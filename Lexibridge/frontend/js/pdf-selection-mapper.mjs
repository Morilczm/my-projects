const MAX_SELECTION_CHARS = 180;

export class PdfSelectionMappingError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "PdfSelectionMappingError";
    this.code = code;
  }
}

function normalizedTextWithOffsets(value, compactWhitespace = false) {
  const source = String(value || "");
  let normalized = "";
  const starts = [];
  const ends = [];
  let pendingWhitespaceStart = -1;
  let pendingWhitespaceEnd = -1;

  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (/\s/u.test(character)) {
      if (compactWhitespace) continue;
      if (normalized && !normalized.endsWith(" ")) {
        pendingWhitespaceStart = pendingWhitespaceStart < 0
          ? index
          : pendingWhitespaceStart;
        pendingWhitespaceEnd = index + 1;
      }
      continue;
    }
    if (pendingWhitespaceStart >= 0) {
      normalized += " ";
      starts.push(pendingWhitespaceStart);
      ends.push(pendingWhitespaceEnd);
      pendingWhitespaceStart = -1;
      pendingWhitespaceEnd = -1;
    }
    const lowered = character.toLocaleLowerCase("en-US");
    for (let offset = 0; offset < lowered.length; offset += 1) {
      normalized += lowered[offset];
      starts.push(index);
      ends.push(index + 1);
    }
  }
  return {source, normalized, starts, ends};
}

function allOccurrences(haystack, needle) {
  const result = [];
  if (!needle) return result;
  let cursor = 0;
  while (cursor <= haystack.length - needle.length) {
    const found = haystack.indexOf(needle, cursor);
    if (found < 0) break;
    result.push(found);
    cursor = found + 1;
  }
  return result;
}

function candidateResult(
  item,
  normalizedItem,
  normalizedStart,
  normalizedLength,
  compactWhitespace,
) {
  const originalStart = normalizedItem.starts[normalizedStart];
  const originalEnd = normalizedItem.ends[normalizedStart + normalizedLength - 1];
  return {
    chunkUid: String(item.chunk_uid || ""),
    selectedText: normalizedItem.source.slice(originalStart, originalEnd),
    selectionStart: originalStart,
    selectionEnd: originalEnd,
    pageNumber: Number(item.page_number || 0),
    blockUid: String(item.block_uid || ""),
    normalizedStart,
    normalizedItemText: normalizedItem.normalized,
    mappingMode: compactWhitespace
      ? "PDF_TEXT_LAYER_COMPACT_WHITESPACE"
      : "PDF_TEXT_LAYER_NORMALIZED_WHITESPACE",
  };
}

function collectCandidates(items, selected, compactWhitespace) {
  const candidates = [];
  for (const item of Array.isArray(items) ? items : []) {
    if (!item || item.selectable !== true || !String(item.chunk_uid || "")) continue;
    const normalizedItem = normalizedTextWithOffsets(item.text, compactWhitespace);
    for (const start of allOccurrences(normalizedItem.normalized, selected)) {
      candidates.push(candidateResult(
        item,
        normalizedItem,
        start,
        selected.length,
        compactWhitespace,
      ));
    }
  }
  return candidates;
}

function disambiguateWithPagePosition(
  candidates,
  selected,
  pagePrefixText,
  pageText,
  compactWhitespace,
) {
  if (!String(pageText || "").trim()) return [];
  const normalizedPage = normalizedTextWithOffsets(
    pageText,
    compactWhitespace,
  ).normalized;
  const normalizedPrefix = normalizedTextWithOffsets(
    pagePrefixText,
    compactWhitespace,
  ).normalized;
  const selectedPageStart = normalizedPrefix.length;
  const selectedOccurrences = allOccurrences(normalizedPage, selected);
  const selectedOrdinal = selectedOccurrences.filter(
    position => position < selectedPageStart,
  ).length;
  if (
    selectedOccurrences.length === candidates.length
    && selectedOrdinal >= 0
    && selectedOrdinal < candidates.length
  ) {
    return [candidates[selectedOrdinal]];
  }
  const positioned = [];

  for (const candidate of candidates) {
    for (const itemPageStart of allOccurrences(
      normalizedPage,
      candidate.normalizedItemText,
    )) {
      const expectedStart = itemPageStart + candidate.normalizedStart;
      if (Math.abs(expectedStart - selectedPageStart) <= 2) {
        positioned.push(candidate);
        break;
      }
    }
  }
  return positioned;
}

export function mapPdfSelectionToReaderItem({
  selectedText,
  pagePrefixText = "",
  pageText = "",
  items = [],
}) {
  const rawSelection = String(selectedText || "");
  const normalizedSelection = normalizedTextWithOffsets(rawSelection).normalized;
  if (!normalizedSelection) {
    throw new PdfSelectionMappingError(
      "PDF_SELECTION_EMPTY",
      "Select one English concept in the PDF text layer.",
    );
  }
  if (rawSelection.length > MAX_SELECTION_CHARS) {
    throw new PdfSelectionMappingError(
      "PDF_SELECTION_TOO_LONG",
      "The PDF selection is longer than the one-concept boundary.",
    );
  }

  let selectedForMapping = normalizedSelection;
  let compactWhitespace = false;
  let candidates = collectCandidates(items, selectedForMapping, false);
  if (candidates.length === 0) {
    selectedForMapping = normalizedTextWithOffsets(rawSelection, true).normalized;
    compactWhitespace = true;
    candidates = collectCandidates(items, selectedForMapping, true);
  }

  if (candidates.length === 0) {
    throw new PdfSelectionMappingError(
      "PDF_SELECTION_NOT_MAPPED",
      "The PDF selection does not map to one governed evidence chunk.",
    );
  }
  if (candidates.length === 1) return candidates[0];

  const positioned = disambiguateWithPagePosition(
    candidates,
    selectedForMapping,
    pagePrefixText,
    pageText,
    compactWhitespace,
  );
  if (positioned.length === 1) return positioned[0];
  throw new PdfSelectionMappingError(
    "PDF_SELECTION_AMBIGUOUS",
    "The PDF selection occurs in more than one governed evidence chunk.",
  );
}

export const PDF_SELECTION_MAX_CHARS = MAX_SELECTION_CHARS;
