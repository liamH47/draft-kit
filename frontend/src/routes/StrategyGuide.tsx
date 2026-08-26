import { Link } from 'react-router-dom'

import { STRATEGIES } from '../content/strategies'

/** A field manual for the strategies people actually run. Reference only:
 *  nothing here changes the board's recommendations — the reader is learning
 *  to recognize the room's behavior as much as planning their own. */
export function StrategyGuide() {
  return (
    <main className="wrap guide">
      <header className="sheet-head">
        <h1>Draft strategies</h1>
        <Link to="/">back to setup</Link>
      </header>
      <p className="muted">
        The most common ways people draft, described faithfully — including the ones this board
        would argue with. Nothing on this page changes the recommendations; it is here so you can
        plan your own build and recognize everyone else's.
      </p>

      <nav className="toc muted">
        <a href="#league-size">league size</a>
        {STRATEGIES.map((s) => (
          <a key={s.id} href={`#${s.id}`}>
            {s.name.toLowerCase()}
          </a>
        ))}
      </nav>

      <section id="league-size" className="strategy">
        <h2>League size changes everything</h2>
        <p>
          Almost every note below comes down to one mechanism: replacement level. In a 6-team
          league, the waiver wire holds startable players all season — scarcity is mostly fake,
          bench floor is worthless, and the winning moves are upside swings and streaming. In a
          12-team league the wire is picked clean, positional cliffs are real and arrive early,
          and depth you drafted is depth you have. The same strategy can be sharp in one room and
          a trap in the other, which is why every entry here says how it bends at both poles.
        </p>
        <p>
          Two calibration notes before the entries. First, every round number below assumes a
          10-12 team draft: in a 6-team room, compress them — round 9 there is pick ~50, the
          middle of round 4 by 12-team count, and the draft may simply end before the late-round
          advice comes due. Second, ADP is 12-team math wherever you get it (public feeds publish
          8-to-14-team series and nothing smaller), so in a small room every listed price
          overstates scarcity: players last rounds past their number, and a green +N on the board
          is often just the format, not a bargain.
        </p>
        <p>
          Team count is not the only dial: every flex or extra WR slot moves replacement the same
          way. A second flex in a 12-team room adds twelve starters, nearly all RB and WR — so the
          league plays two sizes deeper at those positions while staying a 12-team league at QB
          and TE — and a 3-WR lineup at 8 teams puts WR replacement in 12-team territory even
          though everything else on the roster is shallow. Autodraft density is the other
          room-level variable: autodrafters follow the platform's list top-down, which makes
          availability predictable and timing-based plans stronger — a few entries note where.
        </p>
      </section>

      {STRATEGIES.map((s) => (
        <section key={s.id} id={s.id} className="strategy">
          <h2>
            {s.name}
            {s.aka && s.aka.length > 0 && <span className="muted aka"> · aka {s.aka.join(', ')}</span>}
          </h2>
          <p className="thesis">{s.thesis}</p>
          <dl>
            <div>
              <dt>How it works</dt>
              <dd>
                <ul>
                  {s.roundByRound.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </dd>
            </div>
            <div>
              <dt>When it fits</dt>
              <dd>
                <ul>
                  {s.fitsWhen.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </dd>
            </div>
            <div>
              <dt>Shallow league</dt>
              <dd>{s.leagueSize.shallow}</dd>
            </div>
            <div>
              <dt>Deep league</dt>
              <dd>{s.leagueSize.deep}</dd>
            </div>
            {s.autodraft && (
              <div>
                <dt>Autodraft rooms</dt>
                <dd>{s.autodraft}</dd>
              </div>
            )}
            <div>
              <dt>Risks</dt>
              <dd>
                <ul>
                  {s.risks.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </dd>
            </div>
            <div>
              <dt>In draftkit</dt>
              <dd>{s.inDraftkit}</dd>
            </div>
            <div>
              <dt>Where it comes from</dt>
              <dd>{s.provenance}</dd>
            </div>
          </dl>
        </section>
      ))}
    </main>
  )
}
