(function (root, factory) {
  const exported = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = exported;
  if (root) root.LexiFormalWorkflow = exported;
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  const STORAGE_KEY = "lexibridge.formalAlignment.activeRun.v1";
  const PAGE_SIZE = 20;
  const MAX_NETWORK_FAILURES = 3;
  const MIN_POLL_INTERVAL_SECONDS = 1;
  const MAX_POLL_INTERVAL_SECONDS = 10;
  const DEFAULT_POLL_INTERVAL_SECONDS = 2;
  const DEFAULT_POLL_TIMEOUT_MS = 120000;
  const TERMINAL_STATUSES = new Set([
    "ready_for_review",
    "completed_with_warnings",
    "blocked",
    "failed",
  ]);
  const STATUS_ORDER = Object.freeze({
    queued: 0,
    validating: 1,
    processing: 2,
    ready_for_review: 3,
    completed_with_warnings: 3,
    blocked: 3,
    failed: 3,
  });
  const PERSISTED_FIELDS = Object.freeze([
    "source_uid",
    "idempotency_key",
    "run_uid",
    "location",
    "items_url",
    "started_at",
    "last_status",
    "poll_interval_seconds",
    "page",
    "page_size",
  ]);

  function boundedText(value, maximum) {
    return String(value || "").trim().slice(0, maximum);
  }

  function clampPollSeconds(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return DEFAULT_POLL_INTERVAL_SECONDS;
    return Math.max(
      MIN_POLL_INTERVAL_SECONDS,
      Math.min(MAX_POLL_INTERVAL_SECONDS, Math.floor(numeric)),
    );
  }

  function randomUuidFromBytes(bytes) {
    if (!bytes || bytes.length !== 16) throw new Error("Secure random bytes are unavailable.");
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, value => value.toString(16).padStart(2, "0"));
    return [
      hex.slice(0, 4).join(""),
      hex.slice(4, 6).join(""),
      hex.slice(6, 8).join(""),
      hex.slice(8, 10).join(""),
      hex.slice(10, 16).join(""),
    ].join("-");
  }

  function createIdempotencyKey(cryptoApi) {
    if (!cryptoApi) throw new Error("Web Crypto is required.");
    const uuid = typeof cryptoApi.randomUUID === "function"
      ? cryptoApi.randomUUID()
      : randomUuidFromBytes(cryptoApi.getRandomValues(new Uint8Array(16)));
    const key = `ui-formal-alignment-v1-${uuid}`;
    if (key.length > 128) throw new Error("Generated idempotency key exceeds the API limit.");
    return key;
  }

  function emptyPersistedState() {
    return {
      source_uid: "",
      idempotency_key: "",
      run_uid: "",
      location: "",
      items_url: "",
      started_at: "",
      last_status: "",
      poll_interval_seconds: DEFAULT_POLL_INTERVAL_SECONDS,
      page: 1,
      page_size: PAGE_SIZE,
    };
  }

  function sanitizePersistedState(candidate) {
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) return null;
    const sanitized = {
      source_uid: boundedText(candidate.source_uid, 64),
      idempotency_key: boundedText(candidate.idempotency_key, 128),
      run_uid: boundedText(candidate.run_uid, 64),
      location: boundedText(candidate.location, 256),
      items_url: boundedText(candidate.items_url, 256),
      started_at: boundedText(candidate.started_at, 64),
      last_status: boundedText(candidate.last_status, 64),
      poll_interval_seconds: clampPollSeconds(candidate.poll_interval_seconds),
      page: Math.max(1, Math.floor(Number(candidate.page) || 1)),
      page_size: PAGE_SIZE,
    };
    if (!sanitized.source_uid || !sanitized.idempotency_key) return null;
    if (sanitized.run_uid) {
      if (!sanitized.location || !sanitized.items_url) return null;
      if (!sanitized.location.startsWith("/api/document-alignment-runs/")) return null;
      if (!sanitized.items_url.startsWith("/api/document-alignment-runs/")) return null;
    }
    return sanitized;
  }

  function persistedProjection(state) {
    const result = {};
    for (const field of PERSISTED_FIELDS) result[field] = state[field];
    return result;
  }

  function safeClone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function createController(options) {
    const fetchImpl = options && options.fetchImpl;
    const storage = options && options.storage;
    const cryptoApi = (options && options.cryptoApi)
      || (typeof window !== "undefined" ? window.crypto : null);
    const getToken = (options && options.getToken) || (() => "");
    const baseUrl = String((options && options.baseUrl) || "").replace(/\/$/, "");
    const onChange = (options && options.onChange) || (() => {});
    const onAuthFailure = (options && options.onAuthFailure) || (() => {});
    const sleep = (options && options.sleep) || (milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds)));
    const nowIso = (options && options.nowIso) || (() => new Date().toISOString());
    const nowMs = (options && options.nowMs) || (() => new Date().getTime());
    const pollTimeoutMs = Number((options && options.pollTimeoutMs) || DEFAULT_POLL_TIMEOUT_MS);

    if (typeof fetchImpl !== "function") throw new TypeError("fetchImpl is required.");
    if (!storage || typeof storage.getItem !== "function") throw new TypeError("storage is required.");

    let persisted = emptyPersistedState();
    let runtime = {
      mode: "idle",
      run: null,
      items: [],
      pagination: null,
      error: null,
      request_id: "",
      submitting: false,
      polling: false,
      loading_items: false,
      network_failures: 0,
    };
    let startPromise = null;
    let pollPromise = null;
    let itemPromise = null;
    let controller = null;
    let generation = 0;

    function snapshot() {
      return safeClone({ ...persisted, ...runtime });
    }

    function emit() {
      onChange(snapshot());
    }

    function persist() {
      storage.setItem(STORAGE_KEY, JSON.stringify(persistedProjection(persisted)));
    }

    function restore() {
      let parsed = null;
      try {
        parsed = JSON.parse(storage.getItem(STORAGE_KEY) || "null");
      } catch (error) {
        parsed = null;
      }
      const sanitized = sanitizePersistedState(parsed);
      if (!sanitized) {
        storage.removeItem(STORAGE_KEY);
        persisted = emptyPersistedState();
        return false;
      }
      persisted = sanitized;
      persist();
      return true;
    }

    function abortRequest() {
      if (controller) controller.abort();
      controller = null;
    }

    function cancel() {
      generation += 1;
      abortRequest();
      runtime.polling = false;
      runtime.loading_items = false;
      startPromise = null;
      pollPromise = null;
      itemPromise = null;
    }

    function clear() {
      cancel();
      storage.removeItem(STORAGE_KEY);
      persisted = emptyPersistedState();
      runtime = {
        mode: "idle",
        run: null,
        items: [],
        pagination: null,
        error: null,
        request_id: "",
        submitting: false,
        polling: false,
        loading_items: false,
        network_failures: 0,
      };
      emit();
    }

    function safeError(error, fallback) {
      const text = boundedText(error && error.message, 500);
      return {
        status: Number(error && error.status) || 0,
        code: boundedText(error && error.code, 120),
        message: text || fallback,
        request_id: boundedText(error && error.requestId, 128),
      };
    }

    async function readJson(response) {
      try {
        const payload = await response.json();
        return payload && typeof payload === "object" ? payload : {};
      } catch (error) {
        return {};
      }
    }

    function normalizePath(path) {
      const text = boundedText(path, 512);
      if (!text.startsWith("/api/document-alignment-runs")) {
        throw new Error("Formal workflow API path is invalid.");
      }
      return text;
    }

    async function request(path, requestOptions) {
      const normalized = normalizePath(path);
      const headers = { ...((requestOptions && requestOptions.headers) || {}) };
      const token = String(getToken() || "");
      if (token) headers.Authorization = `Bearer ${token}`;
      if (requestOptions && requestOptions.body) headers["Content-Type"] = "application/json";
      controller = typeof AbortController !== "undefined" ? new AbortController() : null;
      let response;
      try {
        response = await fetchImpl(`${baseUrl}${normalized}`, {
          ...(requestOptions || {}),
          headers,
          signal: controller ? controller.signal : undefined,
        });
      } finally {
        controller = null;
      }
      const payload = await readJson(response);
      if (!response.ok) {
        const error = new Error(
          boundedText(
            payload.message || (payload.error && payload.error.message),
            500,
          ) || `HTTP ${response.status}`,
        );
        error.status = response.status;
        error.code = payload.error_code || (payload.error && payload.error.code) || "";
        error.requestId = payload.request_id || response.headers.get("X-Request-ID") || "";
        throw error;
      }
      return {
        data: payload.data || {},
        requestId: payload.request_id || response.headers.get("X-Request-ID") || "",
        location: response.headers.get("Location") || "",
        retryAfter: response.headers.get("Retry-After") || "",
      };
    }

    function applyRun(run) {
      const status = boundedText(run && run.status, 64);
      if (!(status in STATUS_ORDER)) throw new Error("Formal workflow returned an unknown status.");
      if (
        persisted.last_status in STATUS_ORDER
        && STATUS_ORDER[status] < STATUS_ORDER[persisted.last_status]
      ) {
        throw new Error("Formal workflow status regressed.");
      }
      persisted.last_status = status;
      runtime.run = safeClone(run || {});
      runtime.error = null;
      runtime.network_failures = 0;
      runtime.mode = TERMINAL_STATUSES.has(status) ? "terminal" : "polling";
      persist();
      emit();
    }

    function clearForAccessFailure(error) {
      const safe = safeError(error, "Formal workflow is not available.");
      cancel();
      storage.removeItem(STORAGE_KEY);
      persisted = emptyPersistedState();
      runtime.run = null;
      runtime.items = [];
      runtime.pagination = null;
      runtime.error = safe;
      runtime.mode = safe.status === 401
        ? "authentication_required"
        : safe.status === 403
          ? "forbidden"
          : "not_found";
      if (safe.status === 401) onAuthFailure(safe);
      emit();
    }

    async function loadItems(page) {
      if (!persisted.items_url) return null;
      if (itemPromise) return itemPromise;
      const requestedPage = Math.max(1, Math.floor(Number(page) || 1));
      const activeGeneration = generation;
      runtime.loading_items = true;
      emit();
      itemPromise = (async () => {
        try {
          const result = await request(
            `${persisted.items_url}?page=${requestedPage}&page_size=20`,
            { method: "GET" },
          );
          if (activeGeneration !== generation) return null;
          const pagination = result.data.pagination || {};
          persisted.page = Math.max(1, Number(pagination.page) || requestedPage);
          persisted.page_size = PAGE_SIZE;
          runtime.items = Array.isArray(result.data.items) ? safeClone(result.data.items) : [];
          runtime.pagination = safeClone(pagination);
          runtime.error = null;
          runtime.request_id = boundedText(result.requestId, 128);
          persist();
          emit();
          return safeClone(result.data);
        } catch (error) {
          if ([401, 403, 404].includes(Number(error.status))) {
            clearForAccessFailure(error);
          } else {
            runtime.error = safeError(error, "Workflow items could not be loaded.");
            emit();
          }
          return null;
        } finally {
          runtime.loading_items = false;
          itemPromise = null;
          emit();
        }
      })();
      return itemPromise;
    }

    async function poll() {
      if (pollPromise) return pollPromise;
      if (!persisted.run_uid || !persisted.location) return snapshot();
      const activeGeneration = generation;
      const pollingStartedAt = nowMs();
      runtime.polling = true;
      runtime.mode = "polling";
      emit();
      pollPromise = (async () => {
        try {
          while (activeGeneration === generation) {
            if (nowMs() - pollingStartedAt > pollTimeoutMs) {
              runtime.mode = "connection_error";
              runtime.error = { status: 0, code: "POLLING_TIMEOUT", message: "Workflow polling timed out.", request_id: "" };
              emit();
              return snapshot();
            }
            try {
              const result = await request(persisted.location, { method: "GET" });
              if (activeGeneration !== generation) return snapshot();
              runtime.request_id = boundedText(result.requestId, 128);
              applyRun(result.data);
              if (TERMINAL_STATUSES.has(persisted.last_status)) {
                await loadItems(persisted.page || 1);
                return snapshot();
              }
            } catch (error) {
              if ([401, 403, 404].includes(Number(error.status))) {
                clearForAccessFailure(error);
                return snapshot();
              }
              runtime.network_failures += 1;
              runtime.error = safeError(error, "Connection interrupted while checking workflow status.");
              if (runtime.network_failures >= MAX_NETWORK_FAILURES) {
                runtime.mode = "connection_error";
                emit();
                return snapshot();
              }
              emit();
            }
            await sleep(clampPollSeconds(persisted.poll_interval_seconds) * 1000);
          }
          return snapshot();
        } finally {
          runtime.polling = false;
          pollPromise = null;
          emit();
        }
      })();
      return pollPromise;
    }

    async function start(sourceUid) {
      const normalizedSourceUid = boundedText(sourceUid, 64);
      if (!normalizedSourceUid) throw new Error("A governed source_uid is required.");
      if (startPromise) return startPromise;
      if (persisted.source_uid === normalizedSourceUid && persisted.run_uid) return resume();
      if (persisted.source_uid && persisted.source_uid !== normalizedSourceUid) clear();
      if (!persisted.idempotency_key) {
        persisted = {
          ...emptyPersistedState(),
          source_uid: normalizedSourceUid,
          idempotency_key: createIdempotencyKey(cryptoApi),
          started_at: nowIso(),
        };
        persist();
      }
      runtime.mode = "submitting";
      runtime.submitting = true;
      runtime.error = null;
      emit();
      const activeGeneration = generation;
      startPromise = (async () => {
        try {
          const result = await request("/api/document-alignment-runs", {
            method: "POST",
            headers: { "Idempotency-Key": persisted.idempotency_key },
            body: JSON.stringify({ source_uid: normalizedSourceUid }),
          });
          if (activeGeneration !== generation) return snapshot();
          persisted.run_uid = boundedText(result.data.run_uid, 64);
          persisted.location = boundedText(result.location || result.data.status_url, 256);
          persisted.items_url = boundedText(result.data.items_url, 256);
          persisted.poll_interval_seconds = clampPollSeconds(result.retryAfter);
          persisted.last_status = boundedText(result.data.status, 64);
          runtime.run = safeClone(result.data);
          runtime.request_id = boundedText(result.requestId, 128);
          runtime.mode = TERMINAL_STATUSES.has(persisted.last_status) ? "terminal" : "polling";
          persist();
          emit();
          if (TERMINAL_STATUSES.has(persisted.last_status)) await loadItems(1);
          else await poll();
          return snapshot();
        } catch (error) {
          if ([401, 403, 404].includes(Number(error.status))) {
            clearForAccessFailure(error);
          } else {
            runtime.error = safeError(error, "Formal workflow could not be started.");
            runtime.mode = Number(error.status) === 409
              ? "source_changed"
              : Number(error.status) === 422 || Number(error.status) === 400
                ? "request_blocked"
                : "connection_error";
            emit();
          }
          return snapshot();
        } finally {
          runtime.submitting = false;
          startPromise = null;
          emit();
        }
      })();
      return startPromise;
    }

    async function resume() {
      if (!restore()) {
        runtime.mode = "idle";
        emit();
        return snapshot();
      }
      if (!persisted.run_uid) {
        runtime.mode = "pending_submit";
        emit();
        return snapshot();
      }
      return poll();
    }

    async function resumeSubmission() {
      if (!restore() || persisted.run_uid) return resume();
      return start(persisted.source_uid);
    }

    async function retryPolling() {
      runtime.network_failures = 0;
      runtime.error = null;
      if (!persisted.run_uid) return resumeSubmission();
      return poll();
    }

    return Object.freeze({
      start,
      resume,
      resumeSubmission,
      retryPolling,
      loadItems,
      cancel,
      clear,
      getState: snapshot,
    });
  }

  return Object.freeze({
    STORAGE_KEY,
    PAGE_SIZE,
    MAX_NETWORK_FAILURES,
    MIN_POLL_INTERVAL_SECONDS,
    MAX_POLL_INTERVAL_SECONDS,
    TERMINAL_STATUSES,
    PERSISTED_FIELDS,
    createController,
    createIdempotencyKey,
    sanitizePersistedState,
  });
});
