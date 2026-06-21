"""Generate the synthetic intake test set (20 labeled gut-microbiome papers).

Each paper carries the normal PaperOut fields PLUS three ground-truth fields the
intake/test scorer reads:

    expected_label    -- the system Label the SCANNER should emit
                         (ANSWERS | CONTRADICTS | EXTENDS | NOT_RELEVANT)
    expected_category -- the human-facing flag wording for the demo dashboard
                         (question answered | contradiction |
                          previous finding reinforced | knowledge gap filler |
                          not relevant)
    expected_match    -- the profile item id the paper is built to hit
                         (see baskr/data/profile_seed.json), or null

The papers are deliberately written against the seeded "Gordon Lab" profile so a
correctly-working classifier lands on `expected_label`. Run this script to
(re)write both the per-paper files and the combined labeled bundle:

    python -m baskr.scripts.gen_synthetic_intake      # from backend/ on sys.path
    python baskr/scripts/gen_synthetic_intake.py      # or directly

Outputs (under baskr/data/synthetic_intake/):
    paper_01_answers_oq1.json ... paper_20_notrel_soil.json   (20 files)
    testset.json     -- array of all 20 (drop this into the "Run labeled test")
    README.md        -- what the folder is + how to use it
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "synthetic_intake"

# Human-facing flag wording for each system label (kept here so the data files
# are self-describing and the dashboard can show the demo-friendly category).
CATEGORY = {
    "ANSWERS": "question answered",
    "CONTRADICTS": "contradiction",
    "EXTENDS_REINFORCE": "previous finding reinforced",
    "EXTENDS_GAP": "knowledge gap filler",
    "NOT_RELEVANT": "not relevant",
}


def paper(
    slug: str,
    expected_label: str,
    category_key: str,
    expected_match: str | None,
    source: str,
    source_id: str,
    title: str,
    abstract: str,
    journal: str,
    published: str,
    categories: list[str],
) -> dict:
    """Assemble one synthetic paper record (PaperOut fields + ground truth)."""
    doi = f"10.5555/synthetic.{source_id}"
    return {
        "source": source,
        "source_id": source_id,
        "title": title,
        "abstract": abstract,
        "authors": ["Synthetic A. Author", "Demo B. Coauthor"],
        "doi": doi,
        "url": f"https://example.org/{slug}",
        "journal": journal,
        "published": published,
        "categories": categories,
        "uid": f"doi:{doi}",
        # --- ground truth for the scanner scorecard ---
        "expected_label": expected_label,
        "expected_category": CATEGORY[category_key],
        "expected_match": expected_match,
    }


PAPERS: list[dict] = [
    # ----------------------------------------------------------------- ANSWERS
    paper(
        "paper_01_answers_oq1", "ANSWERS", "ANSWERS", "oq_1",
        "pubmed", "90000001",
        "Microbiota maturation causally precedes and drives postnatal weight gain in a germ-free infant-transfer model",
        "Whether gut microbial maturation causes healthy infant growth or merely tracks it has remained unresolved. "
        "We transplanted age-resolved fecal communities from a longitudinal infant cohort into germ-free mouse pups and "
        "applied convergent cross-mapping and time-lagged interventions to separate cause from correlation. Pups receiving "
        "chronologically mature communities gained significantly more lean mass and showed accelerated bone growth than "
        "littermates receiving immature communities sampled from the same infants weeks earlier. Sequential swap experiments "
        "demonstrate that the maturation state of the community, not host age, sets the growth trajectory. We conclude that "
        "microbiota maturation is a causal driver of postnatal growth rather than a passive correlate.",
        "Cell Host & Microbe", "2026-06-19", ["microbiome", "development"],
    ),
    paper(
        "paper_02_answers_oq2", "ANSWERS", "ANSWERS", "oq_2",
        "pubmed", "90000002",
        "Chickpea and green-banana flour are the active microbiota-repairing ingredients in MDCF formulations",
        "Microbiome-directed complementary foods (MDCFs) repair immature gut microbiota in undernourished children, but which "
        "ingredients carry the effect has been unknown. In a four-arm randomized factorial trial we deconstructed an MDCF into "
        "its components and fed single-ingredient prototypes to children with moderate acute malnutrition. Chickpea and "
        "green-banana flour each independently expanded growth-associated taxa (Faecalibacterium prausnitzii, Prevotella copri) "
        "and lifted growth-associated plasma proteins, whereas rice and oil arms did not. The combination was additive. These "
        "results identify the specific complementary-food ingredients that most effectively repair an immature microbiota and "
        "restore growth.",
        "Science Translational Medicine", "2026-06-18", ["microbiome", "nutrition"],
    ),
    paper(
        "paper_03_answers_oq3", "ANSWERS", "ANSWERS", "oq_3",
        "biorxiv", "90000003",
        "Diet-induced expansion of butyrate producers activates hepatic IGF-1 signaling to govern growth",
        "How diet-driven shifts in microbial community composition reach the host pathways that control growth has been a gap. "
        "Using gnotobiotic mice colonized with defined consortia and fed contrasting diets, we traced a mechanistic chain: "
        "fiber-rich diets expanded butyrate-producing Roseburia, elevating portal butyrate, which acted on intestinal "
        "enteroendocrine cells to raise GLP-1 and on hepatocytes to amplify IGF-1 signaling. Blocking the butyrate receptor "
        "abolished the growth signal despite an unchanged community. This maps a specific diet-microbiome-host signaling axis "
        "linking community shifts to the metabolic and immune pathways that govern growth.",
        "biorxiv", "2026-06-17", ["microbiome", "metabolism"],
    ),
    paper(
        "paper_04_answers_oq1", "ANSWERS", "ANSWERS", "oq_1",
        "pubmed", "90000004",
        "Antibiotic-induced arrest of microbiota maturation stunts growth, reversed by maturation rescue",
        "To test causality between microbial community maturation and infant growth we used a controlled perturbation: pulsed "
        "narrow-spectrum antibiotics held the gut community in an immature state in a piglet model that mirrors infant "
        "maturation. Growth velocity fell in lockstep with arrested maturation, and rescue with a maturation-stage-matched "
        "community restored both the community trajectory and catch-up growth. Because the intervention acted on the community "
        "and growth followed, the data establish a causal, not merely correlative, link between microbiota maturation and "
        "healthy postnatal growth.",
        "pubmed", "2026-06-16", ["microbiome", "development"],
    ),
    paper(
        "paper_05_answers_oq2", "ANSWERS", "ANSWERS", "oq_2",
        "pubmed", "90000005",
        "A ranked screen of complementary-food ingredients for repair of immature gut microbiota",
        "Selecting complementary-food ingredients that repair an immature microbiota has been done largely by trial and error. "
        "We screened 22 candidate ingredients ex vivo against fecal communities from undernourished children and validated the "
        "top hits in a randomized feeding study. Soybean, peanut, and chickpea flours ranked highest for restoring "
        "growth-associated taxa and suppressing Enterobacteriaceae, and the in vivo growth-biomarker response tracked the ex "
        "vivo ranking. The work answers which MDCF ingredients most effectively repair an immature microbiota and restore "
        "healthy growth in undernourished children.",
        "Nature Medicine", "2026-06-15", ["microbiome", "nutrition"],
    ),
    # -------------------------------------------------------------- CONTRADICTS
    paper(
        "paper_06_contradicts_asm1", "CONTRADICTS", "CONTRADICTS", "asm_1",
        "pubmed", "90000006",
        "Gut microbiota immaturity is a consequence, not a cause, of childhood undernutrition",
        "A central assumption holds that microbiota immaturity causally contributes to undernutrition. In a 3,000-child birth "
        "cohort with monthly sampling and a sibling-controlled design, we found that drops in microbiota maturity consistently "
        "FOLLOWED rather than preceded growth faltering, and that refeeding restored growth before community maturity recovered. "
        "Instrumental-variable analysis found no causal path from immaturity to undernutrition once dietary intake was "
        "controlled. We conclude microbiota immaturity is a downstream consequence of undernutrition, directly challenging the "
        "view that it is a causal contributor.",
        "Lancet", "2026-06-14", ["microbiome", "epidemiology"],
    ),
    paper(
        "paper_07_contradicts_asm2", "CONTRADICTS", "CONTRADICTS", "asm_2",
        "biorxiv", "90000007",
        "Rational ingredient selection fails to reproducibly promote growth-associated taxa across individuals",
        "It is widely assumed that complementary-food ingredients can be rationally chosen to favor beneficial, "
        "growth-associated taxa over disease-associated ones. Feeding identical rationally-designed ingredient sets to 200 "
        "children, we found the taxonomic response was dominated by each child's baseline community and was essentially "
        "unpredictable: the same ingredient expanded Prevotella in some children and Bacteroides or Enterobacteriaceae in "
        "others, with no reproducible enrichment of growth-associated taxa. Ingredient identity explained under 5% of the "
        "variance. These results contradict the premise that ingredients can be rationally selected to steer the community.",
        "biorxiv", "2026-06-13", ["microbiome", "nutrition"],
    ),
    paper(
        "paper_08_contradicts_fnd2", "CONTRADICTS", "CONTRADICTS", "fnd_2",
        "pubmed", "90000008",
        "MDCF-2 does not outperform standard ready-to-use supplementary food in a multi-country replication trial",
        "An influential trial reported that the microbiome-directed food MDCF-2 outperformed standard ready-to-use "
        "supplementary food (RUSF) on microbiota repair and growth biomarkers. In a pre-registered three-country replication "
        "(n=1,100), MDCF-2 and RUSF produced statistically indistinguishable changes in weight-for-length z-score and in the "
        "growth-associated plasma proteome, and the microbiota-repair signature did not differ between arms. The previously "
        "reported MDCF-2 advantage did not replicate, contradicting the finding that MDCF-2 is superior to RUSF.",
        "NEJM", "2026-06-12", ["microbiome", "nutrition"],
    ),
    paper(
        "paper_09_contradicts_fnd1", "CONTRADICTS", "CONTRADICTS", "fnd_1",
        "biorxiv", "90000009",
        "Discordant-twin microbiota transplants fail to transmit adiposity phenotype in gnotobiotic mice",
        "Transplanting gut microbiota from discordant (lean/obese) twin pairs into germ-free mice was reported to transmit the "
        "donor adiposity phenotype, evidencing a causal microbiome role in host metabolism. Repeating the experiment across "
        "four mouse facilities with 18 twin pairs under standardized diet, we observed no reproducible transmission: recipient "
        "adiposity tracked diet and cage, not donor phenotype, and a meta-analysis of recipients showed a null donor effect. "
        "These findings contradict the claim that discordant-twin microbiota transmit the donor's obese or lean phenotype.",
        "biorxiv", "2026-06-11", ["microbiome", "metabolism"],
    ),
    paper(
        "paper_10_contradicts_asm1", "CONTRADICTS", "CONTRADICTS", "asm_1",
        "pubmed", "90000010",
        "Mendelian-randomization analysis finds no causal effect of microbiota immaturity on child growth",
        "Using host genetic variants that shape gut community maturation as instruments, we performed a Mendelian-randomization "
        "study across three cohorts to test whether microbiota immaturity causally contributes to undernutrition. Genetically "
        "predicted immaturity showed no significant effect on weight-for-age or stunting, while reverse-direction tests "
        "supported growth status driving community state. The genetic evidence argues against a causal contribution of "
        "microbiota immaturity to childhood undernutrition, contradicting the prevailing causal assumption.",
        "pubmed", "2026-06-10", ["microbiome", "genetics"],
    ),
    # --------------------------------------------- EXTENDS (previous finding reinforced)
    paper(
        "paper_11_extends_reinforce_fnd2", "EXTENDS", "EXTENDS_REINFORCE", "fnd_2",
        "pubmed", "90000011",
        "Independent Peruvian cohort replicates MDCF-2 superiority over RUSF on growth-associated biomarkers",
        "In an independent randomized trial in Lima, Peru (n=540) we reproduced the previously reported advantage of "
        "microbiome-directed complementary food MDCF-2 over standard ready-to-use supplementary food: the MDCF-2 arm showed "
        "larger gains in weight-for-length z-score and a stronger rise in the same growth-associated plasma proteins, with a "
        "comparable microbiota-repair signature. Replicating the effect in a new population and food supply reinforces the "
        "finding that MDCF-2 outperforms RUSF for repairing the gut microbiota and improving growth biomarkers.",
        "Nature Medicine", "2026-06-09", ["microbiome", "nutrition"],
    ),
    paper(
        "paper_12_extends_reinforce_fnd1", "EXTENDS", "EXTENDS_REINFORCE", "fnd_1",
        "biorxiv", "90000012",
        "Phenotype transmission from discordant-twin microbiota reproduced with single-colony resolution",
        "We reproduced and strengthened the classic result that gut microbiota from discordant twin pairs transmit the donor's "
        "lean or obese phenotype to gnotobiotic mice. Using barcoded single-colony tracking across 24 twin pairs, recipient "
        "adiposity reliably followed donor phenotype, and we pinpointed the transmissible signal to a defined set of "
        "Bacteroidales strains. The reproduction across a larger panel with strain-level resolution reinforces the causal role "
        "of the microbiome in host metabolism originally demonstrated in the discordant-twin model.",
        "biorxiv", "2026-06-08", ["microbiome", "metabolism"],
    ),
    paper(
        "paper_13_extends_reinforce_fnd2", "EXTENDS", "EXTENDS_REINFORCE", "fnd_2",
        "pubmed", "90000013",
        "Growth benefits of MDCF-2 persist to 24 months in extended follow-up of malnourished children",
        "Extending the original MDCF-2 trial, we followed the Bangladeshi cohort to 24 months. Children who received "
        "microbiome-directed complementary food MDCF-2 maintained their advantage over the standard-supplement arm in linear "
        "growth and retained a more mature, repaired microbiota and elevated growth-associated plasma biomarkers. The durable "
        "benefit reinforces and extends the earlier finding that MDCF-2 outperforms standard ready-to-use supplementary food "
        "at repairing the microbiota and improving growth.",
        "NEJM", "2026-06-07", ["microbiome", "nutrition"],
    ),
    # ----------------------------------------------- EXTENDS (knowledge gap filler)
    paper(
        "paper_14_extends_gap_fnd1", "EXTENDS", "EXTENDS_GAP", "fnd_1",
        "biorxiv", "90000014",
        "Discordant-twin microbiota also transmit intestinal immune tone, extending the metabolic transmission model",
        "Prior work showed discordant-twin microbiota transmit host metabolic phenotype to gnotobiotic mice. We extend that "
        "model into an unexplored dimension: immune phenotype. Recipients of obese-twin communities developed a distinct "
        "intestinal Th17/Treg balance and heightened low-grade inflammation independent of adiposity, revealing a previously "
        "uncharacterized immunological arm of microbiome transmission. This fills a gap adjacent to the established metabolic "
        "finding by showing the transmissible community also reprograms host immune signaling.",
        "biorxiv", "2026-06-06", ["microbiome", "immunology"],
    ),
    paper(
        "paper_15_extends_gap_asm2", "EXTENDS", "EXTENDS_GAP", "asm_2",
        "arxiv", "90000015",
        "A genome-scale metabolic modeling pipeline to rationally design microbiota-repairing food ingredients",
        "The assumption that complementary-food ingredients can be rationally selected to favor growth-associated taxa has "
        "lacked a predictive method. We built a community metabolic-modeling pipeline that simulates how candidate ingredient "
        "glycans are partitioned among gut taxa and predicts which ingredients selectively feed growth-associated species. "
        "Predictions matched ex vivo fermentation for 19 of 22 ingredients. The pipeline supplies the missing rational-design "
        "tool behind ingredient selection, extending the assumption into an actionable, testable framework.",
        "arxiv", "2026-06-05", ["microbiome", "computational"],
    ),
    paper(
        "paper_16_extends_gap_oq3", "EXTENDS", "EXTENDS_GAP", "fnd_2",
        "biorxiv", "90000016",
        "Bile-acid remodeling is a previously unrecognized route by which repaired microbiota improve growth",
        "Beyond short-chain fatty acids, the mechanisms by which a repaired microbiota improves growth remain incompletely "
        "mapped. Studying children and gnotobiotic mice fed microbiome-directed food, we identify microbial bile-acid "
        "deconjugation as a distinct, previously unrecognized axis: repaired communities shifted the bile-acid pool, "
        "activating intestinal FXR signaling that tracked growth-associated plasma biomarkers. This fills a mechanistic gap "
        "left open by prior MDCF work and extends it with a new microbiota-to-host signaling route.",
        "biorxiv", "2026-06-04", ["microbiome", "metabolism"],
    ),
    # ------------------------------------------------------------- NOT_RELEVANT
    paper(
        "paper_17_notrel_vent", "NOT_RELEVANT", "NOT_RELEVANT", None,
        "biorxiv", "90000017",
        "Chemolithoautotrophic microbial communities at deep-sea hydrothermal vents along the East Pacific Rise",
        "We characterized microbial mats colonizing high-temperature hydrothermal vent chimneys using metagenomics and "
        "stable-isotope probing. Sulfur- and hydrogen-oxidizing Epsilonproteobacteria dominated primary production, and we "
        "reconstructed novel chemolithoautotrophic carbon-fixation pathways adapted to steep redox gradients. The findings "
        "illuminate energy flow in chemosynthetic ecosystems independent of sunlight. The work concerns deep-sea geomicrobiology "
        "and has no bearing on host-associated or gut microbial communities.",
        "ISME Journal", "2026-06-03", ["microbiology", "geobiology"],
    ),
    paper(
        "paper_18_notrel_parkinsons", "NOT_RELEVANT", "NOT_RELEVANT", None,
        "pubmed", "90000018",
        "Gut microbiome alpha-synuclein aggregation signatures in elderly Parkinson's disease patients",
        "We profiled the fecal microbiome of 300 older adults with Parkinson's disease and matched controls and related "
        "community composition to enteric alpha-synuclein pathology and motor scores. Depletion of Prevotellaceae and "
        "enrichment of Akkermansia tracked disease severity, suggesting a gut-brain axis contribution to neurodegeneration. "
        "Although this is gut-microbiome research, it concerns adult neurodegenerative disease rather than infant growth, "
        "childhood undernutrition, or complementary-food intervention.",
        "Movement Disorders", "2026-06-02", ["microbiome", "neurology"],
    ),
    paper(
        "paper_19_notrel_histopath", "NOT_RELEVANT", "NOT_RELEVANT", None,
        "arxiv", "90000019",
        "A vision transformer for nuclei segmentation in whole-slide histopathology images",
        "We present a vision-transformer architecture for instance segmentation of cell nuclei in gigapixel whole-slide "
        "images, combining a hierarchical encoder with a boundary-aware loss. On three public histopathology benchmarks the "
        "model improves panoptic quality over convolutional baselines while halving inference cost. The contribution is a "
        "computer-vision method for digital pathology and is unrelated to microbiology, nutrition, or host physiology.",
        "arxiv", "2026-06-01", ["computer-vision", "medical-imaging"],
    ),
    paper(
        "paper_20_notrel_soil", "NOT_RELEVANT", "NOT_RELEVANT", None,
        "biorxiv", "90000020",
        "Nitrogen-fixing rhizosphere microbiome shifts under reduced-tillage maize agriculture",
        "Across a five-year reduced-tillage field trial we tracked the maize rhizosphere microbiome and soil nitrogen cycling. "
        "Reduced tillage enriched diazotrophic Bradyrhizobium and raised nifH gene abundance, correlating with lower synthetic "
        "fertilizer demand and stable yields. The study addresses agricultural soil microbial ecology and crop productivity, "
        "with no connection to human gut microbiota, infant growth, or undernutrition.",
        "biorxiv", "2026-05-31", ["soil-microbiology", "agriculture"],
    ),
]


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Per-paper files (handy for drag-drop into the plain intake stream).
    for p in PAPERS:
        slug = p["url"].rsplit("/", 1)[-1]
        (DATA_DIR / f"{slug}.json").write_text(
            json.dumps(p, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    # Combined labeled bundle (drop this into "Run labeled test").
    (DATA_DIR / "testset.json").write_text(
        json.dumps(PAPERS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # Tally for the README.
    tally: dict[str, int] = {}
    for p in PAPERS:
        tally[p["expected_label"]] = tally.get(p["expected_label"], 0) + 1

    readme = (
        "# Synthetic intake test set\n\n"
        f"{len(PAPERS)} synthetic gut-microbiome papers written against the seeded "
        "lab profile (`baskr/data/profile_seed.json`) to exercise and demo data "
        "ingestion + the classification scanner.\n\n"
        "Each record has the normal paper fields plus ground truth:\n\n"
        "- `expected_label` — the system Label the scanner *should* emit\n"
        "- `expected_category` — the human flag wording for the demo\n"
        "- `expected_match` — the profile item id it is built to hit\n\n"
        "## Label distribution\n\n"
        + "".join(f"- `{k}`: {v}\n" for k, v in sorted(tally.items()))
        + "\n## How to use\n\n"
        "- **Plain ingestion demo:** drag any of the `paper_*.json` files (or all "
        "of them) onto the dev-UI Intake tester — they flow through the real "
        "stream + consumer.\n"
        "- **Scored accuracy test:** upload `testset.json` via *Run labeled test* "
        "in the dev UI. The backend runs each paper through the real scanner and "
        "reports how many it classified correctly on the dashboard scorecard.\n\n"
        "Regenerate with `python baskr/scripts/gen_synthetic_intake.py`.\n"
    )
    (DATA_DIR / "README.md").write_text(readme, encoding="utf-8")

    print(f"Wrote {len(PAPERS)} papers + testset.json + README.md to {DATA_DIR}")
    print("Label distribution:", tally)


if __name__ == "__main__":
    main()
