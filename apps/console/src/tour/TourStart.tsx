import { useEffect } from "react";
import { PageHeader } from "../components/Page";
import { useTour } from "./TourProvider";

/** /tour: starts the guided tour on this organisation's data, then the tour navigates to its first step. */
export function TourStartPage() {
  const { start } = useTour();
  useEffect(() => { void start(); }, [start]);
  return <PageHeader title="How it works" meta="Preparing the tour from your organisation's data." />;
}
