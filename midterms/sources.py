"""Every URL the pipeline reads, in order of preference per dataset.

Mirrors are pinned to a commit so re-runs see identical bytes. Primary
(official) sources come first; the pipeline falls through to the next entry
when a source is unreachable or no longer parses, and records which one it used.
"""

GH = "https://raw.githubusercontent.com"

# unitedstates/congress-legislators: every member of Congress 1789-present,
# one record per term with party (and caucus for independents). Public domain.
LEGISLATORS_SHA = "15530b7d621009eb5fc7eda67f75194d7d91f8c1"  # 2026-10-24
LEGISLATORS = {
    "historical": f"{GH}/unitedstates/congress-legislators/{LEGISLATORS_SHA}/legislators-historical.yaml",
    "current": f"{GH}/unitedstates/congress-legislators/{LEGISLATORS_SHA}/legislators-current.yaml",
}

# jcervas/democracys-data: course-materials repo (Jonathan Cervas, Carnegie
# Mellon) that commits the parsed outputs of several official/academic sources
# we cannot reach directly from this environment. Each file's own build script
# documents its upstream; see SOURCES.md.
CERVAS_SHA = "35dba1bccfa46f4860ecbbf58b2aa88f724e69c0"
_CV = f"{GH}/jcervas/democracys-data/{CERVAS_SHA}/labs/03-elections"
CERVAS = {
    # House Historian "Party Divisions" table parsed to CSV (D, R, total seats)
    "house_party_divisions": f"{_CV}/midterm-loss/data/derived/house_midterms.csv",
    # Jacobson House file 1946-2014 + Clerk/Downballot extension 2016-2024:
    # one row per district-election with dpres (Dem two-party pres share)
    "house_races_dpres": f"{_CV}/house-competition/data/derived/races.csv",
    # Clerk of the House "Statistics of the Congressional Election", 2004-2024,
    # parsed to one row per district with Dem and Rep votes
    "clerk_house_votes": f"{_CV}/house-competition/data/derived/clerk_house.csv",
    # The Downballot / Daily Kos Elections presidential results by CD, 2008-2024
    "pres_by_cd": f"{_CV}/house-competition/data/derived/pres_by_cd.csv",
    # State presidential results 1864-2024 (vote shares) and national totals
    "pres_states": f"{_CV}/historical-campaigns/data/derived/pres_states_1864_2024.csv",
    "pres_national": f"{_CV}/historical-campaigns/data/derived/pres_national.csv",
}

OFFICIAL = {
    "house_party_divisions": "https://history.house.gov/Institution/Party-Divisions/Party-Divisions/",
    "senate_party_divisions": "https://www.senate.gov/history/partydiv.htm",
    "wiki_party_divisions": "https://en.wikipedia.org/wiki/Party_divisions_of_United_States_Congresses",
}

# MIT Election Data + Science Lab, Harvard Dataverse.
DATAVERSE = "https://dataverse.harvard.edu/api"
MEDSL = {
    "house": {"doi": "doi:10.7910/DVN/IG0UN2", "name_contains": "1976-20", "kind": "house"},
    "senate": {"doi": "doi:10.7910/DVN/PEJ5QU", "name_contains": "1976-20", "kind": "senate"},
}
# Verbatim copy of MEDSL 1976-2022 House returns republished by TidyTuesday.
MEDSL_HOUSE_MIRROR = f"{GH}/rfordatascience/tidytuesday/f422450f6519830f6ce0312e5294e3cf110c72ed/data/2023/2023-11-07/house.csv"

# The Downballot (formerly Daily Kos Elections) presidential-by-CD Google
# Sheets, as identified in Cervas's fetch-pres-by-cd.R.
DOWNBALLOT_SHEETS = {
    "2012-2021 lines": ("1XbUXnI9OyfAuhP5P3vWtMuGc5UJlrhXbzZo3AwMuHtk", "0"),
}

# Associated Press, 2026 general election.
AP_ELECTION_DATE = "2026-11-03"
AP_API = f"https://api.ap.org/v3/elections/{AP_ELECTION_DATE}"
AP_RESULTS_PAGES = {
    "house": "https://apnews.com/projects/election-results-2026/?office=House",
    "senate": "https://apnews.com/projects/election-results-2026/?office=Senate",
}
