import "./generator-nav.css";

export type GeneratorProduct = "lithophane" | "housing" | "puzzle" | "puzzle-frame";

export default function GeneratorProductNav({active, onSelect}: {
  active: GeneratorProduct;
  onSelect: (product: GeneratorProduct) => void;
}) {
  return <nav className="generator-nav" aria-label="Rodzaj generatora">
    <section>
      <strong>Litho</strong>
      <div>
        <button className={active === "lithophane" ? "active" : ""} onClick={() => onSelect("lithophane")}>Litofania</button>
        <button className={active === "housing" ? "active" : ""} onClick={() => onSelect("housing")}>Obudowa</button>
      </div>
    </section>
    <section>
      <strong>Puzzle</strong>
      <div>
        <button className={active === "puzzle" ? "active" : ""} onClick={() => onSelect("puzzle")}>Puzzle</button>
        <button className={active === "puzzle-frame" ? "active" : ""} onClick={() => onSelect("puzzle-frame")}>Ramka</button>
      </div>
    </section>
  </nav>;
}
