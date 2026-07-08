interface ConvergenceDiagramProps {
  standardsProgress: number;
  pipelineProgress: number;
  testingProgress: number;
}

function toDasharray(progress: number): string {
  return `${Math.round(progress * 100)} 100`;
}

export function ConvergenceDiagram({
  standardsProgress,
  pipelineProgress,
  testingProgress,
}: ConvergenceDiagramProps) {
  const allArrived = standardsProgress >= 1 && pipelineProgress >= 1 && testingProgress >= 1;

  return (
    <div className="bg-bg-card border border-card-border rounded-[14px] p-6">
      <svg viewBox="0 0 720 160" className="w-full h-auto">
        <path d="M20,30 C 260,30 420,95 660,95" fill="none" stroke="#A79AE8" strokeWidth="3" opacity="0.18" />
        <path d="M20,80 C 260,80 420,95 660,95" fill="none" stroke="#3FBBA0" strokeWidth="3" opacity="0.18" />
        <path d="M20,130 C 260,130 420,95 660,95" fill="none" stroke="#E7975C" strokeWidth="3" opacity="0.18" />

        <path
          data-line="standards"
          pathLength={100}
          d="M20,30 C 260,30 420,95 660,95"
          fill="none"
          stroke="#A79AE8"
          strokeWidth="3.5"
          strokeLinecap="round"
          strokeDasharray={toDasharray(standardsProgress)}
        />
        <path
          data-line="pipeline"
          pathLength={100}
          d="M20,80 C 260,80 420,95 660,95"
          fill="none"
          stroke="#3FBBA0"
          strokeWidth="3.5"
          strokeLinecap="round"
          strokeDasharray={toDasharray(pipelineProgress)}
        />
        <path
          data-line="testing"
          pathLength={100}
          d="M20,130 C 260,130 420,95 660,95"
          fill="none"
          stroke="#E7975C"
          strokeWidth="3.5"
          strokeLinecap="round"
          strokeDasharray={toDasharray(testingProgress)}
        />

        <circle
          cx="660"
          cy="95"
          r="9"
          fill={allArrived ? "#EFC24B" : "none"}
          stroke="#EFC24B"
          strokeWidth="2"
          opacity={allArrived ? 1 : 0.6}
        />
        <circle cx="660" cy="95" r="15" fill="none" stroke="#EFC24B" strokeWidth="1" opacity="0.3" />

        <text x="30" y="22" fill="#A79AE8" fontSize="9.5" fontFamily="ui-monospace, monospace">
          STANDARDS
        </text>
        <text x="30" y="72" fill="#3FBBA0" fontSize="9.5" fontFamily="ui-monospace, monospace">
          PIPELINE
        </text>
        <text x="30" y="146" fill="#E7975C" fontSize="9.5" fontFamily="ui-monospace, monospace">
          TESTING
        </text>
      </svg>
    </div>
  );
}
