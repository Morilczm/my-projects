// Governed direct selection adapter for the self-hosted pdfjs-dist@6.2.108.
import * as pdfjsLib from "../vendor/pdfjs/pdf.mjs";
import {
  mapPdfSelectionToReaderItem,
  PdfSelectionMappingError,
} from "./pdf-selection-mapper.mjs";

const ASSET_ROOT = new URL("../vendor/pdfjs/", import.meta.url);
pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  "pdf.worker.mjs",
  ASSET_ROOT,
).href;

let loadingTask = null;
let documentProxy = null;
let activeSourceUrl = "";
let renderTask = null;
let textLayerTask = null;
let renderGeneration = 0;
let activeSelectionContext = null;

function selectionBelongsToLayer(selection, textLayer) {
  if (!selection || selection.rangeCount !== 1 || selection.isCollapsed) return false;
  const range = selection.getRangeAt(0);
  return textLayer.contains(range.startContainer)
    && textLayer.contains(range.endContainer);
}

function selectionTextContext(selection, textLayer) {
  if (!selectionBelongsToLayer(selection, textLayer)) {
    throw new PdfSelectionMappingError(
      "PDF_SELECTION_OUTSIDE_TEXT_LAYER",
      "Select one concept entirely inside the current PDF page.",
    );
  }
  const range = selection.getRangeAt(0);
  const prefix = document.createRange();
  prefix.selectNodeContents(textLayer);
  prefix.setEnd(range.startContainer, range.startOffset);
  return {
    selectedText: selection.toString(),
    pagePrefixText: prefix.toString(),
    pageText: textLayer.textContent || "",
  };
}

export function capturePdfConceptSelection({selection, textLayer, items}) {
  return mapPdfSelectionToReaderItem({
    ...selectionTextContext(selection, textLayer),
    items,
  });
}

async function closeDocument() {
  activeSelectionContext = null;
  renderGeneration += 1;
  if (renderTask) {
    try { renderTask.cancel(); } catch (_error) { /* already complete */ }
    renderTask = null;
  }
  if (textLayerTask) {
    try { textLayerTask.cancel(); } catch (_error) { /* already complete */ }
    textLayerTask = null;
  }
  if (loadingTask) {
    try { await loadingTask.destroy(); } catch (_error) { /* already closed */ }
  } else if (documentProxy) {
    try { await documentProxy.destroy(); } catch (_error) { /* already closed */ }
  }
  loadingTask = null;
  documentProxy = null;
  activeSourceUrl = "";
}

async function loadDocument(sourceUrl) {
  if (documentProxy && activeSourceUrl === sourceUrl) return documentProxy;
  await closeDocument();
  activeSourceUrl = sourceUrl;
  loadingTask = pdfjsLib.getDocument({
    url: sourceUrl,
    cMapUrl: new URL("cmaps/", ASSET_ROOT).href,
    cMapPacked: true,
    standardFontDataUrl: new URL("standard_fonts/", ASSET_ROOT).href,
    wasmUrl: new URL("wasm/", ASSET_ROOT).href,
    enableXfa: false,
    isEvalSupported: false,
  });
  documentProxy = await loadingTask.promise;
  return documentProxy;
}

function boundedScale(page, preview) {
  const base = page.getViewport({scale: 1});
  const availableWidth = Math.max(320, Number(preview.clientWidth || 0) - 32);
  return Math.max(0.7, Math.min(2.2, availableWidth / base.width));
}

export async function renderPdfConceptPage({
  sourceUrl,
  pageNumber,
  items,
  preview,
  canvas,
  textLayer,
  pageElement,
  statusElement,
}) {
  if (!sourceUrl || !preview || !canvas || !textLayer || !pageElement) {
    throw new Error("PDF.js reader target is incomplete.");
  }
  const generation = ++renderGeneration;
  statusElement.textContent = "正在加载 PDF 页面…";
  statusElement.hidden = false;

  const pdf = await loadDocument(sourceUrl);
  if (generation !== renderGeneration && activeSourceUrl !== sourceUrl) return;
  const activeGeneration = ++renderGeneration;
  const boundedPage = Math.max(1, Math.min(Number(pageNumber || 1), pdf.numPages));
  const page = await pdf.getPage(boundedPage);
  const scale = boundedScale(page, preview);
  const viewport = page.getViewport({scale});
  const outputScale = Math.max(1, Math.min(2, Number(window.devicePixelRatio || 1)));
  const context = canvas.getContext("2d", {alpha: false});

  canvas.width = Math.floor(viewport.width * outputScale);
  canvas.height = Math.floor(viewport.height * outputScale);
  canvas.style.width = `${Math.floor(viewport.width)}px`;
  canvas.style.height = `${Math.floor(viewport.height)}px`;
  pageElement.style.width = `${Math.floor(viewport.width)}px`;
  pageElement.style.height = `${Math.floor(viewport.height)}px`;
  pageElement.style.setProperty("--scale-factor", String(scale));
  textLayer.style.width = `${Math.floor(viewport.width)}px`;
  textLayer.style.height = `${Math.floor(viewport.height)}px`;
  textLayer.style.setProperty("--scale-factor", String(scale));
  textLayer.replaceChildren();

  const transform = outputScale === 1
    ? null
    : [outputScale, 0, 0, outputScale, 0, 0];
  renderTask = page.render({canvasContext: context, viewport, transform});
  const textContent = await page.getTextContent();
  textLayerTask = new pdfjsLib.TextLayer({
    textContentSource: textContent,
    container: textLayer,
    viewport,
  });
  await Promise.all([renderTask.promise, textLayerTask.render()]);
  if (activeGeneration !== renderGeneration) return;

  activeSelectionContext = {
    items: Array.isArray(items) ? items : [],
    textLayer,
  };
  textLayer.onpointerup = () => {
    if (window.Lexi && typeof window.Lexi.capturePdfConceptSelection === "function") {
      window.Lexi.capturePdfConceptSelection();
    }
  };
  statusElement.hidden = true;
  preview.dataset.pdfjsStatus = "READY";
  preview.dataset.pdfjsPage = String(boundedPage);
  preview.dataset.pdfjsVersion = pdfjsLib.version;
}

export function captureCurrentSelection() {
  if (!activeSelectionContext) {
    throw new PdfSelectionMappingError(
      "PDF_SELECTION_READER_NOT_READY",
      "Wait until the PDF text layer is ready.",
    );
  }
  return capturePdfConceptSelection({
    selection: window.getSelection(),
    textLayer: activeSelectionContext.textLayer,
    items: activeSelectionContext.items,
  });
}

export async function destroyPdfConceptReader() {
  await closeDocument();
}

window.LexiPdfReader = {
  version: pdfjsLib.version,
  renderPdfConceptPage,
  captureCurrentSelection,
  destroy: destroyPdfConceptReader,
};
window.dispatchEvent(new CustomEvent("lexibridge:pdfjs-ready"));
