"""Prompt and output schema for turning research into place-specific
invitations.

Kept separate from the provider, exactly like
app/services/question_generation/prompt.py -- the prompt is the part most likely
to be tuned, and isolating it keeps that from touching SDK code.

THREE CORRECTIONS ARE BAKED INTO THIS FILE. Each replaced something that
shipped and was wrong, and each is recorded because the wrong version looked
fine until it was read carefully.

1. READER-FACING QUESTIONS. The first version asked what travellers commonly
   ask about a place, and delivered exactly that: "Is it safe to cross the
   Hillary Bridge if you're scared of heights?", "Should I use the old lower
   bridge or the newer upper one?". Correct research; useless prompts. They are
   addressed to a READER planning a trip, not to a guide standing on the bridge
   -- and the second one asks for advice, which nobody can answer by looking.
   The research goal is unchanged; the OUTPUT is now second-person and present
   tense.

2. GROUNDED-SOUNDING GENERICNESS. A place with nothing findable still produced
   invitations that passed every rule -- second person, present tense, ends in
   "?" -- while carrying no place-specific information at all. "What's this
   place like?" fits anywhere on earth. Fixed in two places, only one of which
   is wording: this prompt demands a self-check, and validation.py structurally
   REQUIRES a specific context_note and a real source URL per invitation. The
   validator is the actual backstop; this file is the first line of defence.

3. WHO DOES THE SEARCHING. This prompt used to run web_search itself. It no
   longer does: research now arrives already done, as sourced findings from a
   dedicated research provider, and this step's only job is judgement. That
   split is not cosmetic -- it is what lets the invitation be checked against
   specific retrieved text rather than against whatever the model remembers,
   and it is why every invitation can now name the finding that produced it.

SECURITY: the findings embedded in the user message are UNTRUSTED WEB TEXT.
The boundary and the exact wording that establishes it live in
app/services/research/sanitize.py, and are included in the system prompt below.
"""

from app.db.models.place_question import PLACE_QUESTION_CONTRIBUTION_KINDS
from app.services.research import sanitize

SYSTEM_PROMPT = f"""You write short invitations asking a guide who is STANDING \
AT A SPECIFIC PLACE RIGHT NOW to report on what is in front of them.

You are given: the name of a real place, where it is, and research about that \
place gathered from the web with citations. You do NOT search. Your job is \
judgement -- deciding which of the researched details are worth asking a person \
who is physically there to check, and phrasing each as an invitation.

{sanitize.UNTRUSTED_DATA_NOTICE}

WHAT MAKES A GOOD INVITATION
The guide is our sensor. They have eyes, a camera, a voice, and local \
experience. A good invitation asks for something only a person AT that place \
can supply, about something the research established is genuinely interesting \
or genuinely uncertain there.

The strongest material is usually:
  - a specific physical feature sources describe -- ask what it looks like now
  - something sources DISAGREE about (opening times, access, condition) -- the \
person at the door can settle it, and that is real field intelligence
  - a local name, nickname, custom or story tied to this exact spot
  - a specific food, item or ritual associated with this place
  - something sources say varies day to day or has recently changed
  - a detail visitors say is easy to miss

GOOD (a temple sources call the "Techie Ganesha", where one source mentions
diamond armour on festival days, and listings disagree on morning opening):
  "Sources say the Ganesha here wears diamond armour on festival days - is it dressed that way today?"
  "Listings disagree on when morning darshan starts - what does the board say?"
  "Do people here still call this the Techie Ganesha?"

GOOD (a suspension bridge):
  "How does the bridge look today - can you take a photo?"
  "Is the crossing busy with mule trains right now?"

GOOD (a tea stall people mention for its apple pie):
  "Is the apple pie on today?"
  "Is the stall open right now?"

BAD -- never produce anything like these:
  "What are the best things to do in Bengaluru?"   (a city, not this place)
  "What is this temple?"                            (a fixed fact, not an observation)
  "How is the weather?"                             (regional, and not about here)
  "Is it safe if you're scared of heights?"         (asks a reader, not the guide)
  "Should I visit in the morning or evening?"       (asks for advice, not a report)
  "How tall is the bridge?"                         (a fixed fact, already knowable)
  "What's this place like?"                         (would read identically anywhere)
  "Tell us about your experience here."             (grounded in nothing)

TWO CHECKS EVERY INVITATION MUST PASS BEFORE YOU INCLUDE IT

  1. THE 50-KILOMETRE TEST. "If this guide were 50km away, would this invitation \
still make sense?" If yes, it is too generic. Rewrite it around a specific \
detail from the research, or drop it. "What's this place like?" and "Tell us \
about your experience here" fail this test at every place on earth.

  2. THE OBSERVABILITY TEST. "Can someone standing here right now see, hear, \
taste, photograph or personally answer this?" If no, drop it. Never ask for a \
fixed fact, a price, a booking detail, or advice.

RULES YOU MUST FOLLOW EXACTLY

- Ground every invitation in the RESEARCH YOU WERE GIVEN. Not in general \
knowledge about the region, not in what seems plausible for a place of this \
type, and not in what you happen to know about somewhere with a similar name. \
If the research says nothing specific about this place, set \
found_information=false and return no invitations. That is a correct and \
common answer -- most places are not written about.
- NEVER INVENT a business, landmark, tradition, story, historical fact, food \
speciality, nickname, or current condition. If it is not in the research, it \
does not exist for your purposes.
- Attribute rather than assert. The research tells you what SOURCES CLAIM, \
which is not the same as what is true. "Sources say X - is that right today?" \
is both honest and a better invitation than stating X as fact.
- Return FEWER invitations rather than padding. Zero is correct when the \
research is thin. Never add one to reach a count.
- Address the guide directly: "you", "here", "today", "right now". Never phrase \
an invitation as a traveller's question to a reader.
- Choose contribution_kind PER INVITATION, from what the research actually \
warrants. Do not give every place the same kind, and do not make everything a \
photo request. Available kinds:
    photo       - the answer is genuinely visual (how something looks today)
    voice       - the answer is a story or personal experience worth hearing
    observation - a specific thing to look at and describe
    experience  - what this place is actually like to be at
    status      - open / closed / accessible / busy right now
- context_note is REQUIRED: one short clause naming the SPECIFIC researched \
detail that makes this worth asking ("sources mention diamond armour on \
festival days", "listings disagree on morning opening"). If you cannot write a \
genuinely specific one from the research, do not include the invitation at \
all. There is no filler option.
- source_urls is REQUIRED: at least one URL, copied exactly from the sources \
listed with the finding you used. Never invent, guess at, shorten or \
reconstruct a URL. If a detail has no source listed, do not use it.
- finding_topic is REQUIRED: the topic label of the research block the detail \
came from, so the invitation can be traced back to it.
- Each invitation must be under 120 characters and end with a question mark.
- Do not produce two invitations that differ only in wording, and do not repeat \
anything in the ALREADY ASKED list -- those have been asked before and adding \
them again wastes the guide's attention.

Return between 0 and 6 invitations."""


def build_user_message(
    place_name: str,
    latitude: float,
    longitude: float,
    description: str | None,
    locality: str | None,
    findings: list,
    already_asked: list[str],
) -> str:
    """Assembles the reasoning input.

    Every finding's text goes inside a delimited untrusted-data block (see
    sanitize). The text was already scrubbed at the provider edge, so the
    delimiter cannot be forged from inside; wrapping here is what tells the
    model where our instructions end and strangers' writing begins.
    """
    lines = [
        "THE PLACE",
        f"Name: {place_name}",
        f"Coordinates: {latitude:.5f}, {longitude:.5f}",
    ]
    if locality:
        lines.append(f"Locality: {locality}")
    if description:
        lines.append(f"Known description: {description}")

    lines.append("")
    lines.append("RESEARCH ABOUT THIS PLACE")
    if not findings:
        lines.append("(none -- no research was available for this place)")
    for finding in findings:
        lines.append("")
        lines.append(f"--- finding topic: {finding.topic} ---")
        lines.append("Sources you may cite for this finding:")
        for source in finding.sources:
            title = f" — {source.title}" if source.title else ""
            lines.append(f"  {source.url}{title}")
        lines.append(sanitize.as_untrusted_block(finding.summary))

    lines.append("")
    if already_asked:
        lines.append("ALREADY ASKED AT THIS PLACE (do not repeat these):")
        lines.extend(f"  - {text}" for text in already_asked)
    else:
        lines.append("ALREADY ASKED AT THIS PLACE: (nothing yet)")

    lines.append("")
    lines.append(
        f"A guide is standing at {place_name} right now. Using ONLY the research "
        "above, write invitations asking them to report on what is in front of "
        "them."
    )
    return "\n".join(lines)


# Structured output schema. `output_config.format` rather than a forced tool
# call: kept from the previous web-search version because the shape is stable
# and the validator in validation.py is written against it.
OUTPUT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            # No `maxItems`: the structured-output validator rejects it for
            # array types ("For 'array' type, property 'maxItems' is not
            # supported"). The count is bounded twice regardless -- the system
            # prompt asks for at most 6, and place_questions._persist_questions
            # enforces settings.place_question_max_count as the real cap.
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question_text": {
                            "type": "string",
                            "description": (
                                "The invitation, addressed directly to the guide who is at "
                                "this place right now. Second person, present tense, "
                                "answerable from what they can see or have just experienced."
                            ),
                        },
                        "contribution_kind": {
                            "type": "string",
                            "enum": list(PLACE_QUESTION_CONTRIBUTION_KINDS),
                            "description": (
                                "How this particular invitation is best answered. Chosen per "
                                "invitation, not applied uniformly across the place."
                            ),
                        },
                        "context_note": {
                            "type": "string",
                            "description": (
                                "REQUIRED. One short clause naming the SPECIFIC researched "
                                "detail that makes this worth asking. If you cannot write a "
                                "genuinely specific one from the research, do not include this "
                                "invitation at all -- there is no empty/filler value."
                            ),
                        },
                        "source_urls": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "REQUIRED, at least one URL copied EXACTLY from the sources "
                                "listed with the finding you used. Never invented, shortened "
                                "or reconstructed."
                            ),
                        },
                        "finding_topic": {
                            "type": "string",
                            "description": (
                                "The topic label of the research block this detail came from, "
                                "so the invitation can be traced back to it."
                            ),
                        },
                    },
                    "required": [
                        "question_text",
                        "contribution_kind",
                        "context_note",
                        "source_urls",
                        "finding_topic",
                    ],
                    "additionalProperties": False,
                },
            },
            "found_information": {
                "type": "boolean",
                "description": (
                    "True only if the supplied research contained meaningful, specific "
                    "information about this exact place. False means the invitation "
                    "list must be empty."
                ),
            },
        },
        "required": ["questions", "found_information"],
        "additionalProperties": False,
    },
}
