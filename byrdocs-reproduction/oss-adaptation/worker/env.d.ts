declare global {
    interface __BaseEnv_Env {
        OSS_ACCESS_KEY_ID: string;
        OSS_ACCESS_KEY_SECRET: string;
        GITHUB_CLIENT_ID: string;
        GITHUB_CLIENT_SECRET: string;
        OCR_TOKEN: string;
    }
}

export {};
