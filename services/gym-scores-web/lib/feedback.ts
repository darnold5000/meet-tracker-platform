/**
 * Tally feedback popup — form id is the segment after https://tally.so/r/
 * @see https://tally.so/r/eqE45q
 */
export const TALLY_FEEDBACK_FORM_ID =
  process.env.NEXT_PUBLIC_TALLY_FEEDBACK_FORM_ID?.trim() || "eqE45q";

export function openTallyFeedback(): void {
  if (typeof window === "undefined") return;
  const id = TALLY_FEEDBACK_FORM_ID;
  if (!id) {
    return;
  }
  const tally = (window as unknown as { Tally?: { openPopup: (formId: string) => void } }).Tally;
  if (tally?.openPopup) {
    tally.openPopup(id);
    return;
  }
  window.open(`https://tally.so/r/${id}`, "_blank", "noopener,noreferrer");
}
