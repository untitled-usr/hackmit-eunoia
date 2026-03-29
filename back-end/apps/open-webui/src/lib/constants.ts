import { browser, dev } from '$app/environment';
import { env } from '$env/dynamic/public';
// import { version } from '../../package.json';

export const APP_NAME = 'Open WebUI';

/** Fixed id of the single system administrator (must match backend SYSTEM_ADMIN_USER_ID). */
export const SYSTEM_ADMIN_USER_ID = '00000000-0000-4000-8000-000000000001';

/** Dev-only: override backend origin (scheme://host:port, no trailing slash). Set via PUBLIC_WEBUI_BACKEND_URL in .env */
function devBackendBaseUrl(): string {
	const fromEnv = env.PUBLIC_WEBUI_BACKEND_URL?.replace(/\/$/, '');
	if (fromEnv) return fromEnv;
	// DevStack 默认后端端口 7920；与页面同 hostname，避免 localhost / 127.0.0.1 混用导致 CORS 问题
	if (browser) return `http://${location.hostname}:7920`;
	return '';
}

export const WEBUI_BASE_URL = browser ? (dev ? devBackendBaseUrl() : ``) : ``;
export const WEBUI_HOSTNAME =
	browser && dev && WEBUI_BASE_URL
		? (() => {
				try {
					return new URL(WEBUI_BASE_URL).host;
				} catch {
					return `${location.hostname}:7920`;
				}
			})()
		: browser && dev
			? `${location.hostname}:7920`
			: ``;
export const WEBUI_API_BASE_URL = `${WEBUI_BASE_URL}/api/v1`;

export const OLLAMA_API_BASE_URL = `${WEBUI_BASE_URL}/ollama`;
export const OPENAI_API_BASE_URL = `${WEBUI_BASE_URL}/openai`;
export const AUDIO_API_BASE_URL = `${WEBUI_BASE_URL}/api/v1/audio`;
export const IMAGES_API_BASE_URL = `${WEBUI_BASE_URL}/api/v1/images`;
export const RETRIEVAL_API_BASE_URL = `${WEBUI_BASE_URL}/api/v1/retrieval`;

export const WEBUI_VERSION = APP_VERSION;
export const WEBUI_BUILD_HASH = APP_BUILD_HASH;
export const REQUIRED_OLLAMA_VERSION = '0.1.16';

export const SUPPORTED_FILE_TYPE = [
	'application/epub+zip',
	'application/pdf',
	'text/plain',
	'text/csv',
	'text/xml',
	'text/html',
	'text/x-python',
	'text/css',
	'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
	'application/octet-stream',
	'application/x-javascript',
	'text/markdown',
	'audio/mpeg',
	'audio/wav',
	'audio/ogg',
	'audio/x-m4a'
];

export const SUPPORTED_FILE_EXTENSIONS = [
	'md',
	'rst',
	'go',
	'py',
	'java',
	'sh',
	'bat',
	'ps1',
	'cmd',
	'js',
	'ts',
	'css',
	'cpp',
	'hpp',
	'h',
	'c',
	'cs',
	'htm',
	'html',
	'sql',
	'log',
	'ini',
	'pl',
	'pm',
	'r',
	'dart',
	'dockerfile',
	'env',
	'php',
	'hs',
	'hsc',
	'lua',
	'nginxconf',
	'conf',
	'm',
	'mm',
	'plsql',
	'perl',
	'rb',
	'rs',
	'db2',
	'scala',
	'bash',
	'swift',
	'vue',
	'svelte',
	'doc',
	'docx',
	'pdf',
	'csv',
	'txt',
	'xls',
	'xlsx',
	'pptx',
	'ppt',
	'msg'
];

export const DEFAULT_CAPABILITIES = {
	file_context: true,
	vision: true,
	file_upload: true,
	web_search: true,
	image_generation: true,
	code_interpreter: true,
	citations: true,
	status_updates: true,
	usage: undefined,
	builtin_tools: true
};

export const PASTED_TEXT_CHARACTER_LIMIT = 1000;

// Source: https://kit.svelte.dev/docs/modules#$env-static-public
// This feature, akin to $env/static/private, exclusively incorporates environment variables
// that are prefixed with config.kit.env.publicPrefix (usually set to PUBLIC_).
// Consequently, these variables can be securely exposed to client-side code.
