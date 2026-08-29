"""Web research, behind a provider-agnostic boundary.

WHAT LIVES HERE: the ability to ask "what does the web say about X?" and get
back a normalized, source-backed finding. Nothing in this package knows what a
Location is, what a PlaceQuestion is, or why anything is being researched --
callers supply a query and get a ResearchFinding.

WHAT DOES NOT LIVE HERE: geographic discovery. Finding out what physically
exists near a coordinate is a different problem with a different right answer
(see app/services/poi_discovery_research/), and conflating the two is what
produced the failure documented in perplexity_provider.py's header.

    base.py                -- the contract every provider implements
    perplexity_provider.py -- the only file that talks to Perplexity
    sanitize.py            -- treats retrieved web text as hostile input

Adding a provider means adding one module here and changing one call site. The
rest of the system depends on ResearchFinding, not on Perplexity.
"""
