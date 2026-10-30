"""Real corpus-backed atlas exploration; no model key or remote inference."""
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.rhyme_atlas import AtlasStore

router = APIRouter(prefix="/api/atlas", tags=["rhyme-atlas"])


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["strict", "balanced", "dirty"] = "dirty"
    kind: Literal["all", "word", "compound", "phrase"] = "all"
    languages: List[Literal["de", "en"]] = Field(default_factory=lambda: ["de", "en"], min_length=1, max_length=2)
    min_syllables: int = Field(1, ge=1, le=64)
    max_syllables: int = Field(32, ge=1, le=64)
    origin: Literal["all", "attested", "constructed"] = "all"
    include_combinations: bool = True
    limit: int = Field(40, ge=1, le=100)

    @model_validator(mode="after")
    def lengths(self):
        if self.min_syllables > self.max_syllables:
            raise ValueError("Die Mindestlänge darf die Höchstlänge nicht überschreiten.")
        return self


class Region(BaseModel):
    model_config = ConfigDict(extra="forbid")
    syllables: int = Field(ge=1, le=128)
    first_family: str = Field(max_length=30)
    last_family: str = Field(max_length=30)
    signature: Optional[str] = Field(None, max_length=500)


class Search(Filters):
    query: str = Field("", max_length=4000)
    region: Optional[Region] = None


class Expand(Filters):
    entry_id: int = Field(ge=1)


class ChainMember(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=500)
    entry_id: Optional[int] = Field(None, ge=1)


class Chain(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field("Eigene Reimfolge", min_length=1, max_length=160)
    members: List[str | ChainMember] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_members(self):
        texts = [member if isinstance(member, str) else member.text for member in self.members]
        if not self.title.strip() or any(not text.strip() or len(text) > 500 for text in texts):
            raise ValueError("Eine Reimfolge braucht einen Titel und nichtleere Reimsegmente mit höchstens 500 Zeichen.")
        return self


def available():
    store = AtlasStore()
    if not store.path.is_file():
        raise HTTPException(503, "Der dauerhafte Atlasbestand wird noch aufgebaut.")
    return store


@router.get("/status")
def status():
    return AtlasStore().status()


@router.get("/map")
def atlas_map(kind: Literal["all", "word", "compound", "phrase"] = "all", languages: str = "de,en",
              origin: Literal["all", "attested", "constructed"] = "all",
              min_syllables: int = Query(1, ge=1, le=64), max_syllables: int = Query(32, ge=1, le=64),
              limit: int = Query(300, ge=10, le=1000)):
    if min_syllables > max_syllables:
        raise HTTPException(422, "Ungültiger Silbenbereich.")
    langs = [value for value in languages.split(",") if value in {"de", "en"}]
    if not langs:
        raise HTTPException(422, "Mindestens eine Sprache auswählen.")
    return available().map({"kind": kind, "languages": langs, "origin": origin, "min_syllables": min_syllables, "max_syllables": max_syllables, "limit": limit})


@router.post("/search")
def search(request: Search):
    return available().search(request.model_dump())


@router.get("/neighborhood")
def neighborhood(syllables: int = Query(ge=1, le=128), first_family: str = Query(max_length=30),
                 last_family: str = Query(max_length=30), kind: Literal["all", "word", "compound", "phrase"] = "all",
                 languages: str = "de,en", origin: Literal["all", "attested", "constructed"] = "all",
                 limit: int = Query(100, ge=1, le=500)):
    langs = [value for value in languages.split(",") if value in {"de", "en"}]
    if not langs:
        raise HTTPException(422, "Mindestens eine Sprache auswählen.")
    return available().neighborhood({"syllables": syllables, "first_family": first_family, "last_family": last_family},
        {"kind": kind, "languages": langs, "origin": origin, "min_syllables": syllables, "max_syllables": syllables, "limit": limit})


@router.post("/expand")
def expand(request: Expand):
    try:
        return available().expand(request.entry_id, request.model_dump(exclude={"entry_id"}))
    except KeyError as error:
        raise HTTPException(404, "Atlaseintrag nicht gefunden.") from error


@router.get("/chains")
def chains():
    return AtlasStore().chains()


@router.post("/chains", status_code=201)
def save_chain(request: Chain):
    try:
        return available().save_chain(request.title, [member if isinstance(member, str) else member.model_dump() for member in request.members])
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
