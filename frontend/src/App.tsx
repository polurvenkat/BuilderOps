import { BrowserRouter, Routes, Route } from "react-router-dom";
import { FleetPage } from "./pages/FleetPage";
import { JourneyPage } from "./pages/JourneyPage";

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<FleetPage />} />
      <Route path="/repos/:id" element={<JourneyPage />} />
    </Routes>
  );
}

export function App({ useMemoryRouter = false }: { useMemoryRouter?: boolean }) {
  if (useMemoryRouter) {
    // Tests supply their own MemoryRouter wrapper around <App useMemoryRouter />
    return <AppRoutes />;
  }
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
