from app.schemas.rhyme import Mode, ModePreset, FeatureTarget, Thresholds, RawWeights

PRESETS: dict[Mode, ModePreset] = {
    Mode.STRICT: ModePreset(
        description="Perfekte Reime: gleiche Silbenzahl, gleicher Stress, enger Vokal- und Tail-Match",
        target=FeatureTarget.RHYME,
        thresholds=Thresholds(maxSyllableDelta=0, maxStressDistance=0, maxVowelDistance=0.20, minTailSimilarity=0.78),
        defaultWeights=RawWeights(stress=0.35, vowelCore=0.35, tail=0.20, syllableFlex=0.10),
    ),
    Mode.BALANCED: ModePreset(
        description="Ausgewogen: leichte Abweichungen in Silben und Stress erlaubt",
        target=FeatureTarget.RHYME,
        thresholds=Thresholds(maxSyllableDelta=1, maxStressDistance=1, maxVowelDistance=0.35, minTailSimilarity=0.58),
        defaultWeights=RawWeights(stress=0.30, vowelCore=0.35, tail=0.25, syllableFlex=0.10),
    ),
    Mode.DIRTY: ModePreset(
        description="Lockerer Reim: Halbreime und Assonanzen werden akzeptiert",
        target=FeatureTarget.RHYME,
        thresholds=Thresholds(maxSyllableDelta=1, maxStressDistance=2, maxVowelDistance=0.50, minTailSimilarity=0.42),
        defaultWeights=RawWeights(stress=0.20, vowelCore=0.40, tail=0.30, syllableFlex=0.10),
    ),
    Mode.MULTISYLLABIC: ModePreset(
        description="Mehrsilbige Reime: betonter Vokal + Ausklang über mehrere Silben",
        target=FeatureTarget.RHYME,
        thresholds=Thresholds(maxSyllableDelta=1, maxStressDistance=1, maxVowelDistance=0.30, minTailSimilarity=0.62),
        defaultWeights=RawWeights(stress=0.30, vowelCore=0.30, tail=0.30, syllableFlex=0.10),
    ),
    Mode.HARDCORE: ModePreset(
        description="Maximale Präzision: nur nahezu identische Ausklänge",
        target=FeatureTarget.RHYME,
        thresholds=Thresholds(maxSyllableDelta=0, maxStressDistance=0, maxVowelDistance=0.15, minTailSimilarity=0.82),
        defaultWeights=RawWeights(stress=0.35, vowelCore=0.40, tail=0.20, syllableFlex=0.05),
    ),
    Mode.END_RHYME: ModePreset(
        description="Endreim: nur der letzte Vokal + Ausklang zählt (klassischer Endreim)",
        target=FeatureTarget.TERMINAL,
        thresholds=Thresholds(maxSyllableDelta=2, maxStressDistance=2, maxVowelDistance=0.22, minTailSimilarity=0.70),
        defaultWeights=RawWeights(stress=0.20, vowelCore=0.35, tail=0.35, syllableFlex=0.10),
    ),
}

def get_preset(mode: Mode) -> ModePreset:
    return PRESETS[mode]

def get_all_presets() -> dict[Mode, ModePreset]:
    return PRESETS
