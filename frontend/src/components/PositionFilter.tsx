const POSITIONS = ['ALL', 'QB', 'RB', 'WR', 'TE', 'K', 'DEF']

type Props = { value: string; onChange: (position: string) => void }

export function PositionFilter({ value, onChange }: Props) {
  return (
    <div className="chips">
      {POSITIONS.map((p) => (
        <button
          key={p}
          type="button"
          className={value === p ? 'chip on' : 'chip'}
          onClick={() => onChange(p)}
        >
          {p}
        </button>
      ))}
    </div>
  )
}
