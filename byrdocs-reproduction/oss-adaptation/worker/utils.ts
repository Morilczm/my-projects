import { Context } from "hono";
import { verify } from "hono/jwt";
import { PrismaD1 } from "@prisma/adapter-d1";
import { PrismaClient } from "./generated/prisma/client";
import { getObject } from "./oss";

export function chunk<T>(array: T[], size: number): T[][] {
    const result = [];
    for (let i = 0; i < array.length; i += size) {
        result.push(array.slice(i, i + size));
    }
    return result;
}

export async function sign(env: Cloudflare.Env, path: string, headers: Headers): Promise<Response> {
    return getObject(env, env.OSS_FILE_BUCKET, path, headers);
}


export async function canDownload(env: Cloudflare.Env, bearer: string | undefined, path: string): Promise<boolean> {
    if (!bearer) return false;
    let payload;
    try {
        payload = await verify(bearer, env.JWT_SECRET, 'HS256');
    } catch {
        return false;
    }
    if (payload.download === true) return true;
    if (typeof payload.id !== "string") return false;
    const prisma = new PrismaClient({ adapter: new PrismaD1(env.DB) });
    const file = await prisma.file.findFirst({
        where: {
            fileName: path,
            uploader: payload.id,
        }
    });
    return file !== null;
}

export function isBupt(cf?: CfProperties): boolean {
    return cf ? (cf.asn === 24350 || cf.asn == 23910 || cf.asn === 4538) : false;
}

export function isSearchEngineBot(c: Context): boolean {
    const ua = c.req.header("User-Agent") || "";
    const bots = ["googlebot", "bingbot", "yandexbot", "baiduspider", "duckduckbot", "slurp", "sogou"];
    return bots.some(bot => ua.includes(bot));
}

export function isMD5(str: string): boolean {
    return /^[a-f0-9]{32}$/i.test(str);
}
