# Interview stage

> Use gpt-oss-20b, Gemini 3 Pro or Claude Sonnet.

1. Craft an initial prompt (example below) to interview with AI:

```
You are helping a hackathon team prepare to interview the users for a prototype.

Project description: <what the team is considering building, and for whom>
Known facts about the users: <roles, workflows, prior conversations>

Produce:

1. Eight to twelve interview questions, broad to specific, designed to surface real workflow rather than confirm the team's assumptions. Mark any leading question.
2. The top five assumptions the team appears to be making about these users, with one concrete way to check each during the interview.

Do not propose solutions.
```

2. Ask for a summary of outcomes and a pruned log of discussion

3. Drill down: 

```
Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask the questions one at a time.

If a question can be answered by exploring the codebase, explore the codebase instead.
```

4. Capture result:

```
Based on the interview notes and the questions we just worked through, produce:

1. A one-paragraph problem statement naming the user, the situation, and the unmet need, without proposing a solution.
2. Three success criteria the prototype must demonstrate by end of day. Each must be observable in a five-minute demo.
3. Three things explicitly out of scope, with a one-line justification each.

Interview notes: <paste>
Working sketch: <paste>
```

5. Ideate:

```
You are helping a hackathon team ideate solutions.

Problem statement: <paste>
Success criteria: <paste>
Out of scope: <paste>
Team skills and constraints: <paste>

Produce:

1. Twelve solution sketches, each two or three sentences. Span "obvious and safe" to "weird and unlikely to work". Number them. Do not pre-rank.
2. For each sketch, one line on what would make it fail in a one-day hackathon.
3. Three pairs of sketches that combine into something stronger, with one line on what the combination adds.

Do not pick a winner.
```

# Instruct stage

> Use gpt-oss-20b, Gemini 3 Pro or Claude Sonnet.

1. Pick tools and working pattern:

```
You are helping a hackathon team pick its tooling for a one-day prototype.

What the team is building: <paste>
Stack and constraints: <paste>
Team skills: <who knows what; especially who has used which AI coding tools>
Demo target: <what the demo must show>
Available tools: <which AI coding tools, models, and APIs the team chose>

Recommend:

1. A primary AI coding tool to drive the implementation, with a one-paragraph justification grounded in skills and demo target.
2. A secondary model from a different provider for adversarial review. Explain in one paragraph what that means here and at what points in the day to invoke it.
3. The two or three configuration files to write before starting (instructions, plan, agent personas, skills), with a one-line description of each.
4. The three tooling questions you are least confident about, and what additional information would resolve each.
```

2. Decide on outcomes, or query multiple models to get different perspectives.

3. Document decision:

```
You are helping a hackathon team commit its working approach to writing.

Problem statement: <paste>
Chosen solution: <one paragraph>
Tooling decision: <paste relevant parts of earlier conversation>
Team size and split: <how many people, working as one group or forking>

Produce a short document (under 400 words) titled "How we are working today" with these sections:

1. Driver tool and why.
2. The one or two configuration files we are writing before starting, and what each contains.
3. The agent personas or roles we are defining.
4. How we run adversarial review: which secondary model, at what points, against what kind of output.
5. How we split the work: one screen with rotating driver, parallel forks, or a hybrid. Be explicit about when we converge.
6. What we are deliberately not doing today, with one line each.

Output Markdown.
```

3. Define repository structure:

```
You are helping a small team set up a repository for a one-day hackathon prototype.

Project description: <what the team is building, what the demo needs to show, what is out of scope>
Stack and constraints: <languages, frameworks, hosting>
Team size and split: <how many people, one group or forked>

Propose a repo layout: a directory tree with a one-line purpose for each top-level entry, plus the three or four files that should exist on day one (README, planning files, configuration). Optimise for a team that needs to onboard each other quickly and produce a recorded demo by end of day.

Then list the three decisions in your proposed layout that you are least sure about, and explain what would change them. Wait for me to react before producing anything else.
```

4. Write agents.md file:

```
# AGENTS.md

## Project
One sentence on what we're building.

## Stack
<languages, frameworks, key libraries>

## Build / test / run
$ <build command>
$ <test command>
$ <run command>

## Conventions
- <code style or structural rule>
- <naming or terminology rule>

## Glossary
<term> = <definition>. NOT <common misuse>.

## Don'ts
- Don't <specific failure mode the team has seen before>.
- Don't <action that requires human approval>.
```

Note: For Co-pilot, add a pointer to `.github/copilot-instructions.md`

5. Pick skills.

- https://github.com/canonical/copilot-collections/: curated for our context, this should be your first stop.
- https://github.com/github/awesome-copilot/: broader selection, useful when the Canonical collection doesn’t have what you need.

If you can't find great skills, generate your own: https://github.com/canonical/copilot-collections/tree/main/skills/generate-agent-skills

# Plan before executing

> Use Claude Opus.

If a change can be described in one setnence, skip planning.

1. Meta-prompt to design implementation plan.

Use https://github.com/gsd-build/get-shit-done if needed.

Or https://github.com/obra/superpowers.

# Execute

> Use Claude Opus.

1. Implemenation of plan.


# Test and validate

> Use Claude Opus, and any other agents for adversarial review.




