"""Prompt and output schema for place-specific contribution research.

Kept in its own module, separate from the provider, exactly like
app/services/question_generation/prompt.py -- the prompt is the part most
likely to be tuned, and isolating it keeps that from touching SDK code.

WHAT CHANGED AND WHY (this replaced an earlier "popular questions" prompt):

The first version asked for the questions travellers commonly ask about a
place, and it did exactly that -- producing things like "Is it safe to cross
the Hillary Bridge if you're scared of heights?" and "Should I use the old
lower bridge or the newer upper bridge?". Those are correct research findings
and completely useless as prompts, because they are addressed to a READER
planning a trip, not to a guide who is physically standing on that bridge right
now. The second one isn't even observable -- it asks for advice, not for
something you can see.

So the research goal is unchanged (find out what people genuinely care about at
this exact place) but the OUTPUT is now the second-person, present-tense form:
an invitation to the person who is there. Web research establishes what matters
here; the invitation asks the guide to report on it from what is in front of
them.

SECOND CORRECTION (this one): a place that has genuinely nothing specific
findable still produced questions that *sounded* fine while being generic
enough to fit any place -- "What's this place like?" would pass every earlier
rule (second person, present tense, answerable, ends in "?") while carrying
zero place-specific information. The fix has two parts, and only one of them
is prompt wording:
  1. This prompt now asks the model to explicitly self-check every invitation
     against "would this still make sense if you swapped in a different
     place?" before including it.
  2. validation.py now REQUIRES a real, non-empty context_note and at least
     one real source URL per invitation, structurally -- not merely asks for
     one. An invitation with nothing specific behind it is not stored,
     regardless of how the model phrases it. That is the actual backstop;
     this prompt is the first line of defense, not the only one.
"""

from app.db.models.place_question import PLACE_QUESTION_CONTRIBUTION_KINDS

RESEARCH_TOOL_MAX_SEARCHES = 4

SYSTEM_PROMPT = """You research one specific place, then write short invitations \
asking a guide who is STANDING AT THAT PLACE RIGHT NOW to report on it.

You will be given the name of a specific place (a bridge, viewpoint, teahouse, \
monastery, market, trail section, campsite, cafe, stupa, and so on) and its \
approximate coordinates.

STEP 1 -- RESEARCH THIS EXACT PLACE.
Use web search to find out what people actually say, ask, photograph and notice \
about THIS place specifically: trip reports, forum threads, reviews, trekking \
guides, blogs. You are looking for what makes this place matter to the people \
who go there -- what they remember, what they check before arriving, what \
surprises them, what changes from day to day.

STEP 2 -- TURN THAT INTO INVITATIONS.
Each invitation must be addressed directly to the guide who is there now, in \
the second person and the present tense, and must be answerable from what they \
can see, hear or do at this moment.

GOOD (for a suspension bridge):
  "How does the bridge look today - can you take a photo?"
  "Is the crossing easy right now, or is it busy with mule trains?"
  "What does the trail look like right where it meets the bridge?"

GOOD (for a well-known tea stall):
  "Is the tea stall open today?"
  "How busy is it right now?"
  "People often stop here - what was it like for you?"

GOOD (for a summit or viewpoint):
  "Is the summit visible from here right now?"
  "Can you take a photo showing what the view looks like today?"

BAD -- never produce anything like these:
  "What are the best things to do in Nepal?"        (about a country, not a place)
  "What is Everest?"                                 (a fact, not an observation)
  "What is the weather in Nepal?"                    (regional, not here)
  "Is it safe if you're scared of heights?"          (asks a reader, not the guide)
  "Should I use the lower or the upper bridge?"       (asks for advice, not a report)
  "How tall is the bridge?"                          (fixed fact, already known)
  "What's this place like?"                          (says nothing that couldn't apply anywhere)
  "Tell us about your experience here."              (generic -- not grounded in anything found)

WHAT KIND OF THING TO ASK ABOUT (use whichever genuinely fits what you found --
never force a place into a category it doesn't have):
  - a specific visual detail (colour, condition, structure, view) worth a photo
  - a before/after or condition check on something known to change (crossing,
    surface, water level, snow, crowding)
  - a specific local business, stall or service people mention being at this spot
  - a specific local story, custom or practice tied to this exact place
  - a personal-experience prompt, when this place is known as a memorable stop
  - a specific food or item people are known to get here
  - a specific overlooked detail travellers say they almost missed
  - whether a specific, named feature is currently open, visible or accessible

Every one of these is worthless without a specific, findable detail behind it.
The list is inspiration for WHAT TO LOOK FOR when you search, not a quota to
fill -- a place that only supports two of these should produce two invitations,
not six padded ones.

BEFORE INCLUDING AN INVITATION, SELF-CHECK IT: "If I swapped in the name of a \
completely different place, would this invitation still read naturally?" If \
yes, it is too generic -- rewrite it around a specific detail your search found, \
or drop it. "What's this place like?" and "Tell us about your experience here" \
both fail this check regardless of which place they are attached to.

RULES YOU MUST FOLLOW EXACTLY:

- Ground every invitation in what your search actually found about THIS place. \
Do not write invitations from general knowledge about the region, or from what \
seems plausible for a place of this type. If search told you nothing specific \
about this place, say so with found_information=false and return no invitations.
- Return FEWER invitations rather than padding. Zero is a correct and expected \
answer. Never invent one to reach a count.
- Every invitation must be answerable RIGHT NOW by someone at the place, from \
direct observation or their own experience there. Never ask for a fixed fact \
(height, history, founding date), for booking or pricing, or for advice.
- Address the guide directly: "you", "here", "today", "right now". Never phrase \
it as a traveller's question to a reader.
- Choose contribution_kind PER INVITATION, based on what this place actually \
warrants. Do not give every place the same kind, and do not make everything a \
photo request. Available kinds:
    photo       - the answer is genuinely visual (how something looks today)
    voice       - the answer is a story or personal experience worth hearing
    observation - a specific thing to look at and describe
    experience  - what this place is actually like to be at
    status      - open / closed / accessible / busy right now
- context_note is REQUIRED for every invitation you include: one short clause \
naming the specific thing your search found that makes this worth asking (e.g. \
"known for its steep drop to the river" or "trekkers mention the tea stall's \
apple pie"). If you cannot write a genuinely specific one, DO NOT include the \
invitation at all -- there is no null or filler option here.
- source_urls is REQUIRED for every invitation: at least one real URL from your \
search that supports context_note. An invitation with no real source behind it \
must not be included.
- Each invitation must be under 120 characters and end with a question mark.
- Do not produce two invitations that differ only in wording.

Return between 0 and 6 invitations."""


def build_user_message(
    place_name: str,
    latitude: float,
    longitude: float,
    description: str | None,
) -> str:
    lines = [
        f"Place: {place_name}",
        f"Approximate coordinates: {latitude:.5f}, {longitude:.5f}",
    ]
    if description:
        lines.append(f"Known description: {description}")
    lines.append("")
    lines.append(
        f"A guide is standing at {place_name} right now. Research this exact place "
        "on the web, then write invitations asking them to report on what is in "
        "front of them."
    )
    return "\n".join(lines)


# Structured output schema. `output_config.format` (rather than a forced tool
# call as extraction/question-generation use) because this request ALSO needs
# the web_search server tool -- tool_choice cannot be forced to a custom tool
# while a server tool must also be free to run.
OUTPUT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            # No `maxItems` here: the structured-output schema validator
            # rejects it for array types ("For 'array' type, property
            # 'maxItems' is not supported"). The count is bounded twice
            # regardless -- the system prompt asks for at most 6, and
            # place_questions._persist_questions enforces
            # settings.place_question_max_count server-side as the real cap.
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
                                "How this particular place is best reported on. Chosen per "
                                "invitation, not applied uniformly."
                            ),
                        },
                        "context_note": {
                            "type": "string",
                            "description": (
                                "REQUIRED. One short clause naming the specific thing research "
                                "established about this place that makes this worth asking. If "
                                "you cannot write a genuinely specific one, do not include this "
                                "invitation in the array at all -- there is no empty/filler value "
                                "for this field."
                            ),
                        },
                        "source_urls": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "REQUIRED, at least one URL. Real sources from your search that "
                                "support context_note. If you have none, do not include this "
                                "invitation in the array at all."
                            ),
                        },
                    },
                    "required": [
                        "question_text",
                        "contribution_kind",
                        "context_note",
                        "source_urls",
                    ],
                    "additionalProperties": False,
                },
            },
            "found_information": {
                "type": "boolean",
                "description": (
                    "True only if search returned meaningful information about this "
                    "specific place. False means the invitation list should be empty."
                ),
            },
        },
        "required": ["questions", "found_information"],
        "additionalProperties": False,
    },
}
