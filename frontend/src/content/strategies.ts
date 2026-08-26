/** The strategy guide's content. Reference only — nothing in this file feeds
 *  the engine, the recommendation score, or the pick order.
 *
 *  Owned by the draft-strategy-educator agent (.claude/agents/). Every entry
 *  answers the same questions; the type is the editorial contract. File order
 *  is page order.
 */

export type Strategy = {
  /** slug; anchor target for the jump-nav */
  id: string
  name: string
  aka?: string[]
  /** one sentence: the bet you are making */
  thesis: string
  /** phase lines, assuming a 10-12 team baseline */
  roundByRound: string[]
  /** scoring/roster shapes where it shines */
  fitsWhen: string[]
  /** how the strategy bends at the size poles — the mechanism is almost
   *  always replacement level */
  leagueSize: {
    shallow: string // 6-8 teams; write to the 6-team pole, 8 interpolates
    deep: string // 12+ teams
  }
  /** how autodraft density bends it — a room variable orthogonal to size;
   *  only where the mechanism is concrete */
  autodraft?: string
  /** in their strongest form; includes recorded dissent from review */
  risks: string[]
  /** running it with what the board actually shows */
  inDraftkit: string
  /** origin + how commonly it is actually run */
  provenance: string
}

export const STRATEGIES: Strategy[] = [
  {
    id: 'bpa',
    name: 'Best Player Available',
    aka: ['value drafting', 'VBD'],
    thesis:
      'Positional scripts leak points, so you take the most valuable player on the board at every pick and let the roster shape itself.',
    roundByRound: [
      'Rounds 1-3: take the biggest gap over replacement, whatever the position — usually the player whose tier is about to vanish.',
      'Rounds 4-8: still value first, but break ties toward the position whose next cliff is closest.',
      'Rounds 9-13: value starts to include need — a fifth WR you will never start is not the best player for your team.',
      "Last rounds: fill required slots and take ceilings; the gaps between the next dozen names are smaller than any projection's error bar.",
    ],
    fitsWhen: [
      'Any scoring format — this is the baseline, not a positional bet',
      'Rooms you cannot read: casual leagues, autodrafters, unfamiliar drafters',
      'You trust your projections more than any pre-set plan',
    ],
    leagueSize: {
      shallow:
        'At 6 teams the trap is raw points: nearly everyone startable comes back around, so "best available" must mean best over replacement — which quietly steers you toward the only assets still scarce at this size, the true bell-cow RBs and at most the top tight end, while the deep positions wait.',
      deep: 'At 12+ this is the environment the math was built for: replacement level sits far down every list, missed tiers do not come back, and the value gaps the method measures are real points.',
    },
    risks: [
      'It is only as good as the projections underneath — season-long point estimates miss a lot, and BPA inherits every miss with full confidence.',
      'It has no opinion on roster construction, so it can leave you thin exactly where the room understood scarcity better than your sheet did.',
      'Mid-draft "best available" is often four players inside a rounding error, and pure BPA offers no tiebreaker.',
    ],
    inDraftkit:
      'This is the board\'s native mode: the pool sorts by value, the Wait cost column prices each pick against what should come back, and the recommendation card leads with "Waiting to pick N costs ~X pts".',
    provenance:
      "The frame is borrowed from real front offices; the fantasy math is Joe Bryant's Value Based Drafting (Footballguys, 1996). Almost everyone runs a version of it knowingly or not — every entry below is a planned deviation from this one.",
  },
  {
    id: 'tiers',
    name: 'Tier-Based Drafting',
    thesis:
      'Order inside a tier is noise but the drop between tiers is real, so you draft to beat the cliffs, not the rankings.',
    roundByRound: [
      'Before the draft: group every position into tiers and stop caring about order inside them.',
      'Every pick: compare tiers, not players — draft from the position whose current tier is nearly empty and whose next tier is a real step down.',
      'When two positions both have tier room, take from the shallower tier and let the deeper one wait a turn.',
      'Late rounds: tiers flatten into a blob; switch to need and upside.',
    ],
    fitsWhen: [
      'Snake drafts with long waits between picks, where "will he come back?" is the whole question',
      'Positions with sharp cliffs that year — TE most years, RB in thin years',
      'Drafters who freeze under a pick clock; a tier is a pre-made decision',
    ],
    leagueSize: {
      shallow:
        'At 6 teams tiers drain slowly — a whole tier can survive two of your turns — so the only cliffs with teeth are at the very top of RB and TE. Below those, waiting is nearly free.',
      deep: 'At 12+ a tier can vanish between your picks, especially at the turn. The tier list doubles as a run detector: when a tier is down to its last name or two, the run has already started.',
    },
    autodraft:
      "Run detection assumes humans who panic; autodrafters never run. In a half-autodraft room, tiers drain on the platform's schedule rather than in bursts — watch the list, not the room's mood.",
    risks: [
      'Tiers inherit every flaw in the rankings beneath them — cluster a bad list and you get confident-looking bad tiers.',
      'The edges are softer than they look: treating a tier break as a wall makes you reach for the last man of one tier when the first man of the next is barely worse.',
      'Public tiers are shared knowledge — in a sharp room everyone sees the same cliff coming, and it arrives before your pick.',
    ],
    inDraftkit:
      "The Tier column shows Boris Chen's tiers wherever he covers a position (numbered on his overall board, so a position's top tier may not read T1), and filtering to a single position draws a border at every tier break, so a dying tier is visible at a glance.",
    provenance:
      'Tier drafting is decades old as a habit; Boris Chen, then a data scientist at the New York Times, put it on rails around 2013 by clustering expert consensus ranks with a Gaussian mixture model. His charts made it a mainstream method, and his tiers are the ones this board shows.',
  },
  {
    id: 'zero-rb',
    name: 'Zero RB',
    aka: ['antifragile drafting'],
    thesis:
      'Early running backs fail at the highest rate of any premium pick, so you buy stable WR/TE/QB production early and harvest the RB chaos later, when injuries hand out starting jobs for free.',
    roundByRound: [
      'Rounds 1-5: no running backs — load WR, take an elite TE or QB where the value falls.',
      'Rounds 6-10: RBs in bulk — pass-catchers, ambiguous backfields, upside jobs; you want volatility, not "safe" mid-round backs.',
      'Rounds 11+: keep adding RB lottery tickets; each one is a claim on a starting job that does not exist yet.',
      'The strategy finishes in-season: the draft built the WR wall, waivers build the RB room.',
    ],
    fitsWhen: [
      'Full PPR, where receptions prop up both your WR wall and the pass-catching RBs you draft late',
      'Lineups with 3 WR or multiple flex spots that let the early WRs all start',
      'Years when the room prices mid-round RBs as if their workloads were safe',
    ],
    leagueSize: {
      shallow:
        "At 6 teams the strategy loses most of its point: startable RBs sit on waivers all season, so anyone can harvest the chaos without spending a draft on it — and the WR wall matters less because everyone's WRs are good. It bends toward plain value drafting.",
      deep: 'At 12+ this is the real version: RB replacement level is bleak, so when a bench lottery ticket hits you own something waivers cannot produce. The downside is equally real — if the tickets miss, mid-tier RBs cost trades and FAAB you do not have.',
    },
    risks: [
      'In years the elite RBs stay healthy they are the safest picks in the draft, and the Zero RB team spends October starting a fourth WR against the bell-cow it refused to pay for.',
      'It is a bet on your in-season speed as much as your draft — run Zero RB and then sleep on waivers and you just have a bad roster.',
      'The market has adjusted since 2013: mid-round RB is no longer systematically cheap, so the discount the strategy was built to collect is smaller than in its famous years.',
      'The payoff arrives late by design; the roster often plays worst in September, which tests nerves in head-to-head leagues.',
    ],
    inDraftkit:
      'Build it on the cheat sheet: F-fade the early RBs you refuse to pay for and T-target your round-6-and-later RB list, then run the front half through the WR filter and the Tier column. On draft night the hot flag shows which cheap backfields the Sleeper market is already chasing.',
    provenance:
      'Shawn Siegele coined it at RotoViz in 2013 — "Zero RB, Antifragility, and the Myth of Value-Based Drafting" — borrowing Taleb\'s antifragility. It was the sharp play of the mid-2010s, the market adjusted, and it now cycles with RB pricing: always a minority play, never gone.',
  },
  {
    id: 'hero-rb',
    name: 'Hero RB',
    aka: ['anchor RB'],
    thesis:
      'You pay up for exactly one bell-cow, then treat the RB middle rounds as a dead zone — Zero RB with an insurance policy.',
    roundByRound: [
      'Round 1, sometimes 2: one true three-down back — the hero must be a workhorse, not merely the best RB left.',
      'Rounds 2-5: no more RBs; build WR, TE and QB like a Zero RB team.',
      'Rounds 6-10: RB2 and RB3 from the value bin — pass-catchers and upside jobs, the same shopping list Zero RB uses.',
      "Late: more RB lottery tickets, and the hero's handcuff if the price is fair.",
    ],
    fitsWhen: [
      "Half-PPR and standard, where the elite back's touchdown-and-volume edge outweighs another receiver",
      'Rooms that start WR-heavy and let a top-tier RB fall to you',
      'Start-2-RB lineups where the full Zero RB punt feels too thin',
    ],
    leagueSize: {
      shallow:
        'At 6 teams the hero is the whole strategy: an elite bell-cow is one of the few assets the waiver wire can never replace, while the depth behind him is barely better than what is free. This may be the most natural plan a shallow league allows.',
      deep: 'At 12+ the dead-zone logic sharpens but so does the failure mode: the hero is your only RB anyone would trade for, and patching an RB2 from round 7 onward is far harder when eleven other rosters drafted the position.',
    },
    risks: [
      'A single point of failure by design — the strategy is named after the one player whose injury ends it. A Zero RB team can lose anyone; a Hero RB team cannot.',
      'The dead zone is a market observation, not a law: in years the round-3-to-5 backs hit, you skipped the best value on the board on principle.',
      'It needs the board to cooperate in round 1 — if the true workhorses are gone at your pick, "hero" quietly becomes "reach".',
    ],
    inDraftkit:
      'T-target the few backs you would accept as the hero and F-fade the dead-zone RBs behind them. After round 1, the RB Tier column and Wait cost show exactly what skipping the middle is costing — the number this strategy bets stays low.',
    provenance:
      'No single coiner: it hardened out of the Zero RB debate in the late 2010s, largely in best-ball rooms, as the compromise for drafters who bought the dead-zone evidence but not the full punt. Under either name it is now arguably the most-run named RB plan in home leagues.',
  },
  {
    id: 'robust-rb',
    name: 'Robust RB',
    aka: ['zero WR', 'RB-heavy'],
    thesis:
      "Startable running backs run out long before startable receivers, so you corner the scarce position in the first three rounds and shop the draft's deepest aisle — WR — for the rest of the night.",
    roundByRound: [
      'Rounds 1-3: two RBs minimum, often three — locked-in workhorses, not committee guesses.',
      'Rounds 4-7: pivot to the WR board and take the best of a deep group; an elite TE fits here too.',
      'Rounds 8+: WR volume, a QB, one more RB for depth.',
      'Late: handcuff your workhorses before someone else buys them as lottery tickets.',
    ],
    fitsWhen: [
      'Standard and half-PPR, where carries and touchdowns out-earn receptions',
      'Start-2-RB lineups with little flex, which force every roster to field two real backs',
      "Rooms full of Zero RB and Hero RB drafters, who hand you the position's whole top shelf",
    ],
    leagueSize: {
      shallow:
        'At 6 teams the back half of the plan is free — late-round and waiver WRs are genuinely startable, so skipping WR early costs little. Two bell-cows is one of the few durable edges a shallow league offers.',
      deep: 'At 12+ the WR aisle is thinner than the plan assumes: skip the position for four rounds in a 12-team PPR and every WR slot may open the season a tier light. The RB moat is real, but now the WR cliff is too.',
    },
    risks: [
      "It concentrates capital in the draft's most fragile asset class — two early RBs is double the injury exposure Zero RB exists to avoid.",
      'Full PPR tilts the math against it: receptions lift WR scoring, and the late-WR discount the plan relies on shrinks.',
      'It was built in the workhorse era; committee backfields mean the "scarce volume" being cornered is smaller than it used to be.',
    ],
    inDraftkit:
      "Filter to RB and play the Tier column's tier breaks — Robust RB is drafted off the RB cliffs. Once two backs are banked, the value flag and green ADP +N badges point at the receivers the room is letting slide.",
    provenance:
      'The oldest plan on this page — in the 2000s workhorse era it was simply called drafting. The name is a retronym coined in the mid-2010s, once Zero RB needed a counterpart to argue with, and it returns to fashion every year the early RBs stay healthy.',
  },
  {
    id: 'late-round-qb',
    name: 'Late-Round QB',
    thesis:
      'In 1-QB leagues the weekly gap between an elite QB and the tenth-best is usually smaller than what that early pick buys at RB or WR, so you take the position last and spend the savings.',
    roundByRound: [
      'Rounds 1-8: no quarterback; spend everything on RB, WR and TE.',
      'Rounds 9-12: one QB from the leftovers — prefer rushing upside, the trait that lets a cheap QB finish expensive.',
      'Last rounds: optionally a second QB on a different bye; in shallower leagues even that is a luxury.',
    ],
    fitsWhen: [
      '1-QB lineups, any scoring — the entire edge is that only one starts',
      '4-point-passing-TD scoring, which flattens the QB curve further',
      'Rooms where two or three managers pay up early for QBs and deepen your discount',
    ],
    leagueSize: {
      shallow:
        'At 6 teams this is barely a strategy — it is arithmetic: with six starters and a couple of backups rostered, the wire holds a top-10 QB every week of the season, so a late pick or a weekly stream costs you almost nothing. Paying a middle-round pick for a QB at this size is pure luxury spending.',
      deep: 'At 12+ it still works, but the net is thinner: QB13 as your floor is uncomfortable, byes bite, and one injury can mean streaming the true dregs. The discount is usually still worth taking; it just stops being free.',
    },
    autodraft:
      "Autodrafters take QBs exactly when the platform's list says, so there is no early-QB panic to survive; the discount is at its most reliable in rooms where half the picks are on rails.",
    risks: [
      'Superflex and 2-QB leagues invert this completely — there, QBs are the scarcest asset on the board, and running Late-Round QB is punting your most valuable lineup slot.',
      'Some seasons the elite-QB gap is not small: when two or three QBs post historic rushing seasons, the position decides leagues and the "discount" was the expensive kind.',
      'Its own success eroded it — in rooms where everyone waits, there is no discount left to collect, and the last mid-tier QB can vanish in a two-pick run.',
      "Recorded dissent from the board's own numbers: on current projections the thesis only holds below the very top — QB1 to QB10 spans ~70 points, more than the same picks buy at WR, while QB3 to QB15 spans ~33 — so waiting is cheap once the top one or two QBs are gone, not before.",
    ],
    inDraftkit:
      'Filter to QB and watch the Tier column — the whole plan is not being last out of the middle tier. A QB Wait cost that stays low all night is the strategy working; when it spikes, the room is starting the run.',
    provenance:
      'JJ Zachariason made the case book-length in "The Late Round Quarterback" (2012) and spent the next decade backing it with data at numberFire. It went from contrarian to near-consensus in 1-QB leagues — which is much of why superflex formats caught on as the counter.',
  },
  {
    id: 'te-barbell',
    name: 'The TE Barbell',
    aka: ['elite TE', 'punt TE'],
    thesis:
      'Tight end scoring is a cliff — a couple of players are weekly mismatches and the rest are interchangeable — so the only prices worth paying are the top or nearly free, never the middle.',
    roundByRound: [
      'Elite pole, rounds 1-3: take one of the two or three true difference-makers, count him as a WR1 in your lineup math, and never roster a backup for him.',
      'Punt pole, rounds 10+: skip the position entirely, then take one or two cheap swings on profile — athletic, new team, red-zone role.',
      'Both poles: rounds 4-9 are the forbidden zone, where a real pick buys a marginally better version of what is nearly free.',
    ],
    fitsWhen: [
      "TE-premium scoring, which widens the elite pole's weekly edge",
      "Full PPR, where the elite TEs' target volume is worth the most",
      'Plain 1-TE lineups with no premium, which push most drafters to the punt pole',
    ],
    leagueSize: {
      shallow:
        'At 6 teams punt harder: the wire always holds a serviceable TE, so the forbidden zone grows, and the elite pole survives only for the clear top player at a fair price — his edge over free shrinks when free is decent.',
      deep: "At 12+ both poles sharpen: the elite TE's gap over the twelfth starter is at its widest, and the punt gets grimmer because streaming TE in a 12-team league means genuinely bad weeks. The no-middle rule binds hardest here.",
    },
    risks: [
      'The elite pole fails ugly: an early pick spent on a TE who finishes fifth at the position returns a point or two a week over the last starting TE — a fraction of what a round-2 pick usually buys.',
      'The punt pole is a weekly tax you agreed to in August — in close matchups the TE hole is often the exact margin.',
      'The middle is not always wrong: some years the breakout lives in the TE4-TE8 band, and the barbell has you fading precisely the players who return the most.',
    ],
    inDraftkit:
      'Filter to TE and the Tier column makes the argument itself — the top tier is a couple of names, then the shelf. T-tag your elite target or F-fade the middle tiers on the cheat sheet, and let the TE Wait cost confirm what waiting actually costs.',
    provenance:
      'Nobody owns this one; it is the community\'s accumulated read of the TE scoring curve. The punt pole is ancient, the elite pole hardened in the Gronkowski years, and "barbell" is the best-ball era\'s name for holding both at once. Most drafters live on one pole without naming it.',
  },
  {
    id: 'handcuffing',
    name: 'Handcuffing',
    thesis:
      "A workhorse's direct backup inherits a starting job the moment one player goes down, so you buy that insurance at draft prices before an injury sets the market.",
    roundByRound: [
      'Rounds 1-9: nothing to do — handcuffing is a late-draft act.',
      'Rounds 10+: cuff your own early backs first, prioritizing backfields with one clear next man up over committees.',
      "Alternative school: buy other teams' premium handcuffs instead — upside tickets, not insurance.",
      "In-season: a cuff is droppable the moment the starter's role or health stabilizes; the slot is rented, not owned.",
    ],
    fitsWhen: [
      'Deep benches, where a zero-point insurance slot is affordable',
      'Rosters built on one or two expensive backs — Hero and Robust builds with something to insure',
      'Leagues with fierce FAAB or waiver competition, where the backup costs several times more the week the injury happens',
    ],
    leagueSize: {
      shallow:
        'At 6 teams classic insurance-cuffing is mostly wasted: when a starter goes down the wire usually offers a startable back anyway, so the payout the cuff insures is roughly free — the slot is better spent on an upside swing. Only the elite cuffs — a true bell-cow one snap from a bell-cow job — earn a spot.',
      deep: 'At 12+ this is where handcuffing earns its keep: waivers will not save you, every contender is one RB injury from crisis, and the backup you rostered in round 12 can become the most-wanted player in the league overnight.',
    },
    risks: [
      'Most cuffs never matter — the slot scores zero all season, and in leagues where bench depth wins weeks that is a real, quiet cost.',
      'The clear backup often is not: vacated work splits across a committee and the insurance pays out at half value.',
      'Cuffing your own back doubles your stake in one offense — if the line or the scheme collapses, starter and insurance sink together.',
    ],
    inDraftkit:
      'Injury badges (IR/PUP/Q) mark the backfields already in flux, and the hot flag shows which backups the Sleeper market grabbed today. T-tag your cuffs on the cheat sheet so they resurface in the late rounds, when the quick-entry box is doing the work.',
    provenance:
      "The oldest term in this guide — magazine-era vocabulary from the 2000s workhorse decade, when every stud had one obvious backup. Committees have blunted the classic version; the modern sharp form, buying other people's cuffs as cheap upside, is now at least as common.",
  },
  {
    id: 'streaming',
    name: 'Streaming DEF/K',
    thesis:
      'Defense and kicker scoring is driven more by weekly matchup than by roster talent, so you draft the positions last and rent the best matchup off waivers all season instead of owning anyone.',
    roundByRound: [
      'Every round until the end: draft neither — a DEF or K taken early is a skill player you did not get.',
      'Last two rounds: one defense chosen for its opening two or three weeks of matchups, kicker with the final pick.',
      'In-season: drop and re-add by matchup each week; the draft pick was just the first stream.',
    ],
    fitsWhen: [
      'Shallow and mid-size leagues, where good streams sit on waivers every week',
      'Leagues without transaction fees or tight add limits',
      'Rosters that need every bench slot for skill-position upside',
    ],
    leagueSize: {
      shallow:
        "At 6 teams streaming is close to solved: most of the league's defenses are free every week, the top matchup is nearly always available, and an early DEF/K pick is simply a wasted pick.",
      deep: 'At 12+ the pool thins — with twelve defenses rostered, the obvious stream is often claimed by Wednesday. Streaming still beats paying up for most drafters, but it becomes a real weekly job with real whiff weeks, and some 12-team drafters buy one round earlier for a set-and-forget unit.',
    },
    risks: [
      'Some years an elite defense scores like a skill player for four months; the punt means you were never in line for it.',
      'It is weekly homework with a deadline — miss a waiver run and you start a bad matchup you chose by default.',
      'Transaction costs are the hidden price: in FAAB or per-move-fee leagues, fifteen weeks of streams is not free.',
    ],
    inDraftkit:
      'Filter to DEF or K in the closing rounds and take from the top of the list — the recommendation score already holds both positions back until the last few rounds, so no tagging is needed. The weekly half of streaming happens on your league site, not on this board.',
    provenance:
      "Streaming grew up on r/fantasyfootball: quickonthedrawl's weekly defense-streaming threads (mid-2010s) proved the matchup math to a mass audience, and Subvertadown's predictive models carried it forward. Once a message-board sharp play, it is now near-default advice.",
  },
  {
    id: 'upside',
    name: 'Upside Drafting',
    aka: ['late-round fliers', 'ceiling drafting'],
    thesis:
      "A late pick's floor is available on waivers all season anyway, so the only thing worth drafting late is a ceiling.",
    roundByRound: [
      'Early rounds: unaffected — this strategy is about the back half of your draft.',
      'Once starters are set, around rounds 8-10: stop drafting known-role veterans whose best case is mediocrity.',
      'Late rounds: take paths to volume — ambiguous backfields, second-year receivers, new starters — and grade each pick by its best case, not its likeliest one.',
      'In-season: churn fast; a flier that has not flashed in a month becomes the next flier.',
    ],
    fitsWhen: [
      'Deep benches — more tickets to the same lottery',
      'Best-ball and tournament formats, where only ceilings get paid',
      'Any redraft league, honestly: the logic runs on replacement level, not scoring',
    ],
    leagueSize: {
      shallow:
        'At 6 teams this is the only sane use of a late pick — the floor players you would draft instead are, by definition, on waivers all year. The payoff shrinks with the stakes, though: your hit is startable, but so is whatever your rivals lift off the wire the same week.',
      deep: 'At 12+ upside has a real price: benches are where injury replacements live, and a roster of pure lottery tickets can reach week 6 with nothing to start. The hits also matter more at this size — a flier who becomes a weekly starter is a moat — so balance the bench rather than abandoning the idea.',
    },
    risks: [
      'Variance cuts both ways: a bench of fliers can all miss, leaving you with nothing to start and nothing to trade at midseason.',
      '"Upside" is the most misapplied word in drafting — hype and highlight reels get graded as ceiling, while boring paths to volume, which hit more often, get skipped.',
      'It quietly assumes waivers will cover your floor; in deep leagues that assumption is the whole risk.',
    ],
    inDraftkit:
      'The late-round flags are the tooling: hot marks players the Sleeper market is adding today, ▲ marks a price rising across markets, and value marks players lasting past their worth. T-tag your fliers on the cheat sheet so the recommendation score pushes them when their round arrives.',
    provenance:
      'Folk wisdom with no coiner, sharpened by the best-ball era: large-field tournaments pay only ceilings, which turned "your last five picks decide your season" into a measurable claim. Sharp drafters run it implicitly; casual rooms still draft floor late.',
  },
  {
    id: 'adp-arbitrage',
    name: 'ADP Arbitrage',
    aka: ['market-delta drafting'],
    thesis:
      'ADP is a price, not a ranking, so you profit from the gap: take players the market underprices at the latest pick they should survive to, and let overpriced names be someone else\'s problem.',
    roundByRound: [
      'Before the draft: mark everyone your sheet likes better than his market price — your buy list — and everyone the market likes better than you do, who you will simply never own.',
      'Every pick: prefer the largest your-value-over-market gap that will not survive to your next turn.',
      'Timing is the skill: take a target at the last pick you believe he lasts to, not the first pick you want him.',
      'Mid-draft, exploit the room too — a position run leaves the neglected position trading below its price for a round or more.',
    ],
    fitsWhen: [
      "Home leagues drafting off one platform's default list, where cross-market gaps go unpunished",
      'Drafters who keep their own projections or paste in a ranking source they trust',
      'Any scoring — the edge is informational, not positional',
    ],
    leagueSize: {
      shallow:
        'At 6 teams the prices themselves are wrong before you start: every public ADP feed is built from 10-14-team drafts — none publishes a 6-team series — and with half the room gone, quarterbacks, tight ends and defenses last far beyond their listed price. Most of your buys survive the short gaps between picks anyway, so arbitrage flattens into "never reach": collect the systematic discounts the format hands you, and never pay list price for a onesie position.',
      deep: 'At 12+ the timing half is the whole game: nearly two full rounds can pass between your picks at the rail, so knowing a player sits five picks past his price is often the difference between owning him and never seeing him again.',
    },
    autodraft:
      "Autodrafters are the perfect counterparty: they walk the platform's ranking list top-down, so availability at your pick stops being a forecast and becomes a schedule. In a half-autodraft room, cross-platform price gaps are guaranteed to go unpunished — know which platform's list the sleeping half is drafting from.",
    risks: [
      "Your valuations have to actually beat the market's — arbitrage against a sharper consensus is just reaching with extra confidence.",
      'ADP describes other drafts, not yours: one manager who loves your target makes the blended price meaningless in your room.',
      'Delta-chasing can quietly assemble a roster of players the market disliked for reasons it understood and you did not.',
    ],
    inDraftkit:
      'This is what the board\'s market machinery is for: ADP ±N shows the live gap (a green +N means still on the board past his price), Consensus #N flags where the board disagrees with the ranking lists via ↑/↓, ▲▼ mark prices moving across the five markets, and a pasted list joins the consensus under its own name.',
    provenance:
      "No coiner — it is price-versus-value thinking imported from betting and finance, made practical once public ADP feeds like FantasyFootballCalculator's existed, and sharpened by the best-ball era's closing-line-value habit. Most experienced drafters run a loose version; running it systematically is rarer.",
  },
]
