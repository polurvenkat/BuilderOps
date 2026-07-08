import { useParams } from "react-router-dom";

export function JourneyPage() {
  const { id } = useParams<{ id: string }>();
  return <div data-testid="journey-page">{id}</div>;
}
