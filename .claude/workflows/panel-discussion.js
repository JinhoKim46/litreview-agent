export const meta = {
  name: 'panel-discussion',
  description: 'Run one round of the multi-field professor panel discussion evaluating this tool',
  phases: [
    { title: 'Opening Statements' },
    { title: 'Free Discussion' },
    { title: 'Moderator Synthesis' },
  ],
}

// args shape (see references/docs/panel_discussion/PROTOCOL.md):
//   { round: number, topic_focus?: string,
//     professors: [{ name, field, persona }, ...] (5-8 entries),
//     max_discussion_rounds?: number (default 3), min_discussion_rounds?: number (default 2) }
//
// Returns the round's full synthesized result -- this script never writes to
// disk (workflow scripts have no filesystem access); the calling session
// persists the returned object as that round's document and updates
// state.json afterward.

const STATEMENT_SCHEMA = {
  type: 'object',
  properties: {
    name: { type: 'string' },
    field: { type: 'string' },
    opening_statement: { type: 'string' },
    key_concerns: { type: 'array', items: { type: 'string' } },
    usability_verdict: { type: 'string' },
  },
  required: ['name', 'field', 'opening_statement', 'key_concerns', 'usability_verdict'],
}

const DISCUSSION_TURN_SCHEMA = {
  type: 'object',
  properties: {
    name: { type: 'string' },
    remarks: { type: 'string' },
    responds_to: { type: 'array', items: { type: 'string' } },
    wants_to_continue: { type: 'boolean' },
    extension_reason: { type: ['string', 'null'] },
  },
  required: ['name', 'remarks', 'responds_to', 'wants_to_continue'],
}

const MODERATOR_DECISION_SCHEMA = {
  type: 'object',
  properties: {
    continue_discussion: { type: 'boolean' },
    reasoning: { type: 'string' },
  },
  required: ['continue_discussion', 'reasoning'],
}

const SYNTHESIS_SCHEMA = {
  type: 'object',
  properties: {
    round: { type: 'number' },
    per_professor_summary: {
      type: 'array',
      items: {
        type: 'object',
        properties: { name: { type: 'string' }, field: { type: 'string' }, summary: { type: 'string' } },
        required: ['name', 'field', 'summary'],
      },
    },
    cross_cutting_themes: { type: 'array', items: { type: 'string' } },
    tensions_or_disagreements: { type: 'array', items: { type: 'string' } },
    recommended_tool_adaptations: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          change: { type: 'string' },
          rationale: { type: 'string' },
          raised_by: { type: 'array', items: { type: 'string' } },
        },
        required: ['change', 'rationale'],
      },
    },
    markdown_transcript: { type: 'string' },
  },
  required: ['round', 'per_professor_summary', 'cross_cutting_themes', 'recommended_tool_adaptations', 'markdown_transcript'],
}

const professors = args.professors
const maxRounds = args.max_discussion_rounds || 3
const minRounds = args.min_discussion_rounds || 2

phase('Opening Statements')
const statements = (await parallel(professors.map((p) => () =>
  agent(
    `You are ${p.name}, ${p.persona} (field: ${p.field}). You are one panelist in a recurring multi-field ` +
    `expert panel evaluating a research-review CLI tool called "litreview-agent" (formerly prisma-flow) -- a ` +
    `Claude-Code-driven, multi-method evidence-synthesis pipeline (systematic review, scoping review, ` +
    `systematic mapping study, reconnaissance briefs, living-review mode, field packs). Explore the actual ` +
    `repository (README, CLAUDE.md, docs/ROADMAP.md, the methods/*.json and packs/*.json manifests, and the ` +
    `.claude/commands/litreview-*.md command files most relevant to your field) using Read/Grep/Glob/Bash. ` +
    `Then give your genuine, critical opening statement as a domain expert: would this tool actually be ` +
    `usable and credible for a real review in your field? What's missing, wrong, or surprising relative to ` +
    `your field's own methodological norms? ${args.topic_focus || ''}`,
    { label: `statement:${p.name}`, phase: 'Opening Statements', schema: STATEMENT_SCHEMA }
  )
))).filter(Boolean)

log(`${statements.length}/${professors.length} opening statements collected`)

phase('Free Discussion')
let transcript = statements
  .map((s) => `**${s.name}** (${s.field}): ${s.opening_statement}\nKey concerns: ${s.key_concerns.join('; ')}\nVerdict: ${s.usability_verdict}`)
  .join('\n\n')

let roundNum = 0
while (roundNum < maxRounds) {
  roundNum++
  const turns = (await parallel(professors.map((p) => () =>
    agent(
      `You are ${p.name}, ${p.persona} (field: ${p.field}), continuing this expert panel discussion. Full ` +
      `transcript so far:\n\n${transcript}\n\nThis is free-discussion round ${roundNum}. Respond to specific ` +
      `points other panelists raised -- agree, push back, build on, or raise a new angle grounded in your own ` +
      `field's norms -- do not just restate your opening statement. Say whether you think the discussion has ` +
      `more ground to cover for you (wants_to_continue) or has run its course.`,
      { label: `discuss-r${roundNum}:${p.name}`, phase: 'Free Discussion', schema: DISCUSSION_TURN_SCHEMA }
    )
  ))).filter(Boolean)

  transcript += `\n\n--- Round ${roundNum} ---\n` + turns.map((t) => `**${t.name}**: ${t.remarks}`).join('\n\n')

  const anyExtensionRequested = turns.some((t) => t.wants_to_continue && t.extension_reason)
  const majorityDone = turns.filter((t) => !t.wants_to_continue).length > turns.length / 2

  if (roundNum >= minRounds && majorityDone && !anyExtensionRequested) break

  if (roundNum >= minRounds) {
    const modDecision = await agent(
      `You are the panel moderator. Full transcript so far:\n\n${transcript}\n\nRound ${roundNum} of free ` +
      `discussion just completed (target 2-3 rounds, hard cap ${maxRounds}). Decide whether to run another ` +
      `discussion round or end now and move to synthesis. All rights over ending/extending are reserved by ` +
      `you as moderator -- weigh whether genuinely new ground is still being covered against just letting it ` +
      `run indefinitely.`,
      { label: `moderator-decision-r${roundNum}`, phase: 'Free Discussion', schema: MODERATOR_DECISION_SCHEMA }
    )
    if (!modDecision.continue_discussion) break
  }
}

phase('Moderator Synthesis')
const synthesis = await agent(
  `You are the panel moderator. Full transcript of round ${args.round} (professors: ` +
  `${professors.map((p) => `${p.name} (${p.field})`).join(', ')}):\n\n${transcript}\n\nWrite the round's ` +
  `official record: a clean, well-organized Markdown transcript (opening statements + discussion, attributed ` +
  `by name/field), a per-professor one-paragraph summary, cross-cutting themes, genuine tensions/` +
  `disagreements between panelists (do not manufacture false consensus), and a concrete list of recommended ` +
  `tool adaptations this round's discussion actually surfaced, each with rationale and which panelist(s) ` +
  `raised it. Be honest and specific -- vague praise is not useful input for adapting the tool.`,
  { label: 'moderator-synthesis', phase: 'Moderator Synthesis', schema: SYNTHESIS_SCHEMA }
)

// round: args.round must come AFTER the ...synthesis spread -- the
// moderator's own structured output also has a `round` field (needed so its
// prompt can refer to "round N"), and nothing guarantees the model echoes
// args.round back consistently. The caller-supplied round number is the
// only authoritative one; never let the model's copy silently win.
return { professors, discussion_rounds_run: roundNum, ...synthesis, round: args.round }
