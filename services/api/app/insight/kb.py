"""
The retrieval side of the brief.

Deliberately small and deliberately TF-IDF. A vector database would be one more
container to keep alive during a demo, and at this corpus size it would not
retrieve anything different. Say that out loud in the write-up — choosing the
simpler mechanism on purpose reads better than reaching for the fashionable one.

Every entry needs a real source. An unsourced line in here becomes an unsourced
claim in a brief, which is exactly the failure mode the whole design exists to
prevent. Replace these with passages from the OneAquaHealth deliverables and
your national water authority's guidance as you find them.
"""
from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

KB: list[dict] = [
    {
        "id": "LIT-DO-1",
        "text": "Dissolved oxygen below about 5 mg/L causes measurable stress in most "
                "freshwater fish, and sustained levels below 3 mg/L lead to mortality in "
                "sensitive species. Warm water holds less oxygen, so heat and organic "
                "load compound each other.",
        "source": "EU Freshwater Fish Directive 78/659/EEC; standard limnological guidance",
    },
    {
        "id": "LIT-TURB-1",
        "text": "Turbidity spikes after rainfall indicate suspended solids washed off "
                "impervious surfaces. Suspended particles shield micro-organisms from UV "
                "and from disinfection, so turbidity is used operationally as a proxy "
                "indicator for microbial load in surface water.",
        "source": "WHO Guidelines for Drinking-water Quality, turbidity chapter",
    },
    {
        "id": "LIT-CSO-1",
        "text": "In catchments with combined sewers, heavy rainfall can exceed system "
                "capacity and discharge untreated wastewater directly to the stream. "
                "These overflow events are the dominant short-term driver of faecal "
                "indicator bacteria in urban watercourses.",
        "source": "EU Urban Waste Water Treatment Directive 91/271/EEC context",
    },
    {
        "id": "LIT-BLOOM-1",
        "text": "Cyanobacterial blooms are favoured by water temperatures above roughly "
                "20 degC combined with elevated nutrients and low flow. Some strains "
                "produce toxins that affect dogs and livestock drinking at the bank "
                "well before there is any risk to people.",
        "source": "WHO Guidelines on recreational water quality, cyanobacteria volume",
    },
    {
        "id": "LIT-NO3-1",
        "text": "Nitrate in surface water above 11.3 mg/L as nitrogen indicates "
                "significant agricultural or wastewater input. Nitrate is a nutrient "
                "driver of eutrophication and is regulated in drinking water abstraction.",
        "source": "EU Nitrates Directive 91/676/EEC",
    },
    {
        "id": "LIT-BMWP-1",
        "text": "The BMWP scheme assigns families of macroinvertebrates a score from 1 "
                "to 10 by pollution sensitivity. ASPT, the average score per taxon, is "
                "more robust to sampling effort than the raw total. ASPT below about 4.5 "
                "indicates an organically degraded reach.",
        "source": "Biological Monitoring Working Party scheme; Armitage et al. 1983",
    },
    {
        "id": "LIT-ONEHEALTH-1",
        "text": "One Health treats human, animal and ecosystem health as a single "
                "interdependent system. For urban freshwater this means a degraded "
                "stream is not only an ecological loss: it is a shared exposure pathway "
                "through recreation, domestic animals, food production and vector habitat.",
        "source": "WHO/FAO/WOAH/UNEP One Health Joint Plan of Action",
    },
    {
        "id": "LIT-VECTOR-1",
        "text": "Slow-moving, nutrient-enriched urban water bodies provide breeding "
                "habitat for mosquito species that transmit West Nile virus and, in "
                "southern Europe, for Aedes albopictus. Stagnation matters more than "
                "absolute pollution level for vector production.",
        "source": "ECDC vector surveillance guidance",
    },
    {
        "id": "LIT-AMR-1",
        "text": "Wastewater-influenced streams act as reservoirs and mixing grounds for "
                "antimicrobial resistance genes. Surface water monitoring is increasingly "
                "used as an early indicator of resistance circulating in a population.",
        "source": "EU One Health action plan against antimicrobial resistance",
    },
    {
        "id": "LIT-CITSCI-1",
        "text": "Citizen-generated stream assessments are reliable at the level of "
                "presence and coarse abundance of indicator families when observers are "
                "given a key and a fixed protocol. Accuracy degrades sharply for "
                "species-level identification, which is why family-level indices are the "
                "standard target for volunteer monitoring.",
        "source": "Published freshwater citizen-science validation studies",
    },
    {
        "id": "LIT-TEMP-1",
        "text": "Urban streams run warmer than rural reference reaches because of runoff "
                "from heated impervious surfaces, reduced riparian shade and effluent "
                "inputs. Elevated baseline temperature narrows the margin before a heat "
                "wave triggers an oxygen crash.",
        "source": "Urban stream syndrome literature; Walsh et al. 2005",
    },
    {
        "id": "LIT-RECREATION-1",
        "text": "Direct contact with contaminated surface water is associated with "
                "gastrointestinal, skin, ear and respiratory symptoms. Risk concentrates "
                "in children and in people with occupational contact, and is highest in "
                "the days immediately following heavy rainfall.",
        "source": "WHO Guidelines on recreational water quality, volume 1",
    },
]

_CORPUS = [e["text"] for e in KB]
_VEC = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
_MATRIX = _VEC.fit_transform(_CORPUS)


def retrieve(query: str, k: int = 4, min_score: float = 0.02) -> list[dict]:
    """Top-k knowledge entries above a similarity floor. Never pads to k."""
    if not query.strip():
        return []
    sims = cosine_similarity(_VEC.transform([query]), _MATRIX)[0]
    order = sims.argsort()[::-1][:k]
    return [
        {**KB[i], "score": round(float(sims[i]), 4)}
        for i in order
        if sims[i] >= min_score
    ]
