import { XMLParser } from "fast-xml-parser";

type OssEnv = Pick<Cloudflare.Env,
    "OSS_ENDPOINT" | "OSS_REGION" | "OSS_FILE_BUCKET" | "OSS_DATA_BUCKET" |
    "OSS_ACCESS_KEY_ID" | "OSS_ACCESS_KEY_SECRET"
>;

const parser = new XMLParser({
    ignoreAttributes: false,
    attributeNamePrefix: "@_",
    textNodeName: "#text",
});

function hex(bytes: ArrayBuffer): string {
    return Array.from(new Uint8Array(bytes), (value) => value.toString(16).padStart(2, "0")).join("");
}

function encode(value: string): string {
    return encodeURIComponent(value).replace(/[!'()*]/g, (character) => `%${character.charCodeAt(0).toString(16).toUpperCase()}`);
}

function encodeKey(key: string): string {
    return key.split("/").map(encode).join("/");
}

function encodeQuery(value: string): string {
    return encode(value);
}

function compare(a: string, b: string): number {
    return a < b ? -1 : a > b ? 1 : 0;
}

async function sha256(value: string | ArrayBuffer): Promise<string> {
    const bytes = typeof value === "string" ? new TextEncoder().encode(value) : value;
    return hex(await crypto.subtle.digest("SHA-256", bytes));
}

async function hmac(key: ArrayBuffer | Uint8Array, value: string): Promise<ArrayBuffer> {
    const cryptoKey = await crypto.subtle.importKey("raw", key, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    return crypto.subtle.sign("HMAC", cryptoKey, new TextEncoder().encode(value));
}

function getObjectUrl(env: OssEnv, bucket: string, key: string, query = new URLSearchParams()): URL {
    const endpoint = new URL(env.OSS_ENDPOINT);
    endpoint.hostname = `${bucket}.${endpoint.hostname}`;
    endpoint.pathname = `/${encodeKey(key)}`;
    endpoint.search = query.toString();
    return endpoint;
}

async function signedRequest(
    env: OssEnv,
    bucket: string,
    key: string,
    method: string,
    query = new URLSearchParams(),
    headers = new Headers(),
    body?: BodyInit,
): Promise<Response> {
    const url = getObjectUrl(env, bucket, key, query);
    const now = new Date();
    const amzDate = now.toISOString().replace(/[:-]|\.\d{3}/g, "");
    const date = amzDate.slice(0, 8);
    const payloadHash = body === undefined ? await sha256("") : await sha256(await new Response(body).arrayBuffer());
    headers.set("x-amz-content-sha256", payloadHash);
    headers.set("x-amz-date", amzDate);

    const canonicalHeaders = new Map<string, string>([
        ["host", url.host],
        ["x-amz-content-sha256", payloadHash],
        ["x-amz-date", amzDate],
    ]);
    for (const [name, value] of headers) {
        const lowerName = name.toLowerCase();
        if (lowerName !== "authorization" && lowerName !== "host") {
            canonicalHeaders.set(lowerName, value.trim().replace(/\s+/g, " "));
        }
    }
    const sortedHeaders = [...canonicalHeaders].sort(([a], [b]) => compare(a, b));
    const canonicalHeaderText = sortedHeaders.map(([name, value]) => `${name}:${value}\n`).join("");
    const signedHeaders = sortedHeaders.map(([name]) => name).join(";");
    const canonicalQuery = [...query.entries()]
        .map(([name, value]) => [encodeQuery(name), encodeQuery(value)] as const)
        .sort(([aKey, aValue], [bKey, bValue]) => compare(aKey, bKey) || compare(aValue, bValue))
        .map(([name, value]) => `${name}=${value}`)
        .join("&");
    const canonicalRequest = [method, url.pathname, canonicalQuery, canonicalHeaderText, signedHeaders, payloadHash].join("\n");
    const scope = `${date}/${env.OSS_REGION}/s3/aws4_request`;
    const stringToSign = ["AWS4-HMAC-SHA256", amzDate, scope, await sha256(canonicalRequest)].join("\n");
    const dateKey = await hmac(new TextEncoder().encode(`AWS4${env.OSS_ACCESS_KEY_SECRET}`), date);
    const regionKey = await hmac(dateKey, env.OSS_REGION);
    const serviceKey = await hmac(regionKey, "s3");
    const signingKey = await hmac(serviceKey, "aws4_request");
    const signature = hex(await hmac(signingKey, stringToSign));
    headers.set("Authorization", `AWS4-HMAC-SHA256 Credential=${env.OSS_ACCESS_KEY_ID}/${scope}, SignedHeaders=${signedHeaders}, Signature=${signature}`);

    return fetch(url, { method, headers, body, redirect: "manual" });
}

async function checkResponse(response: Response): Promise<Response> {
    if (response.ok) return response;
    const body = await response.text();
    throw new Error(`OSS ${response.status}: ${body.slice(0, 500)}`);
}

export async function headFile(env: OssEnv, key: string): Promise<{ size: number; etag: string } | null> {
    const response = await signedRequest(env, env.OSS_FILE_BUCKET, key, "HEAD");
    if (response.status === 404) return null;
    await checkResponse(response);
    return { size: Number(response.headers.get("content-length") || 0), etag: response.headers.get("etag") || "" };
}

export async function getObject(env: OssEnv, bucket: string, key: string, requestHeaders = new Headers()): Promise<Response> {
    const headers = new Headers();
    for (const name of ["range", "if-match", "if-none-match", "if-modified-since", "if-unmodified-since"]) {
        const value = requestHeaders.get(name);
        if (value) headers.set(name, value);
    }
    const response = await signedRequest(env, bucket, key, "GET", new URLSearchParams(), headers);
    if ([404, 304, 412, 416].includes(response.status)) return response;
    await checkResponse(response);
    return response;
}

export async function deleteFile(env: OssEnv, key: string): Promise<void> {
    const response = await signedRequest(env, env.OSS_FILE_BUCKET, key, "DELETE");
    await checkResponse(response);
}

export async function startMultipart(env: OssEnv, key: string): Promise<string> {
    const query = new URLSearchParams([["uploads", ""]]);
    const response = await checkResponse(await signedRequest(env, env.OSS_FILE_BUCKET, key, "POST", query));
    const parsed = parser.parse(await response.text()) as { InitiateMultipartUploadResult?: { UploadId?: string } };
    const uploadId = parsed.InitiateMultipartUploadResult?.UploadId;
    if (typeof uploadId !== "string" || !uploadId) throw new Error("OSS did not return an upload ID");
    return uploadId;
}

export async function uploadPart(env: OssEnv, key: string, uploadId: string, partNumber: number, file: Blob): Promise<string> {
    const query = new URLSearchParams([["partNumber", String(partNumber)], ["uploadId", uploadId]]);
    const headers = new Headers({ "Content-Type": file.type || "application/octet-stream" });
    const response = await checkResponse(await signedRequest(env, env.OSS_FILE_BUCKET, key, "PUT", query, headers, file));
    const etag = response.headers.get("etag");
    if (!etag) throw new Error("OSS did not return an ETag for the uploaded part");
    return etag;
}

export async function completeMultipart(
    env: OssEnv,
    key: string,
    uploadId: string,
    parts: Array<{ partNumber: number; etag: string }>,
): Promise<{ size: number; etag: string }> {
    const xml = `<CompleteMultipartUpload>${[...parts].sort((a, b) => a.partNumber - b.partNumber).map(({ partNumber, etag }) => {
        const quotedEtag = etag.startsWith('"') ? etag : `"${etag}"`;
        return `<Part><PartNumber>${partNumber}</PartNumber><ETag>${quotedEtag}</ETag></Part>`;
    }).join("")}</CompleteMultipartUpload>`;
    const query = new URLSearchParams([["uploadId", uploadId]]);
    const response = await checkResponse(await signedRequest(
        env,
        env.OSS_FILE_BUCKET,
        key,
        "POST",
        query,
        new Headers({ "Content-Type": "application/xml" }),
        xml,
    ));
    const parsed = parser.parse(await response.text()) as { CompleteMultipartUploadResult?: { ETag?: string } };
    const etag = parsed.CompleteMultipartUploadResult?.ETag || "";
    const object = await headFile(env, key);
    if (!object) throw new Error("Completed OSS object could not be found");
    return { size: object.size, etag: etag || object.etag };
}

export async function abortMultipart(env: OssEnv, key: string, uploadId: string): Promise<void> {
    const query = new URLSearchParams([["uploadId", uploadId]]);
    await checkResponse(await signedRequest(env, env.OSS_FILE_BUCKET, key, "DELETE", query));
}
