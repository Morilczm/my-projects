# Student Demo Script

## Goal

Demonstrate course terminology search, evidence viewing, learning records, feedback, and personal workspace boundaries.

For a real course pilot, use this demo script together with `pilot_package/student_manual.md`, `pilot_package/privacy_and_risk_notice.md`, and `pilot_package/student_feedback_form.md`. Demo terminology should be treated as a walkthrough, not as a guarantee of real-course accuracy.

## Account

- Email: `student@lexibridge.local`
- Password: `Student1234`

## Steps

1. Log in as the student and open `Student Workspace`.
   Expected: admin and teacher-only actions are not visible.

2. Select `SP101 - Signal Processing Basics`.
   Expected: the course terminology search area is active.

3. Search `Fourier Transform`.
   Expected: the SP101 card for `Fourier Transform / 傅里叶变换` appears. `Hash Table` evidence should not appear in this course result.

4. Open the card detail.
   Expected: it displays English term, Chinese term, concept explanation, English evidence, Chinese evidence, citation, confidence score, alignment status, risk note, AI provider status, and updated time.

5. Inspect formula evidence status.
   Expected: if `FORMULA_OCR_PROVIDER=none`, formula-related evidence is marked as requiring formula OCR rather than showing fabricated LaTeX.

6. Favorite the card.
   Expected: the card appears in Favorites.

7. Mark the card as mastered.
   Expected: the learning record changes to mastered.

8. Search `Hash Table` inside SP101.
   Expected: it should not appear as a signal-processing course card.

9. Submit feedback on the `Fourier Transform` card.
   Expected: the page confirms that feedback was submitted and the teacher can see it in Quality Control / Student Feedback.

10. Upload a personal learning document.
    Expected: the UI states that personal materials are private and will not enter the official course knowledge base.

11. Open personal task status.
    Expected: personal jobs show queued/running/completed/failed state.

12. Export review materials if the current plan allows it.
    Expected: Basic/Pro can export; Free users receive an upgrade or quota message.

## Talking Points

- The platform is not a generic translator. The student sees evidence-backed bilingual terminology cards.
- Pending or evidence-missing cards are visible as risky and should be used carefully.
- Personal uploads are private by default and do not affect course-public terminology.
