import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import RhymeSearch from "./components/RhymeSearch";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RhymeSearch />
  </StrictMode>
);
