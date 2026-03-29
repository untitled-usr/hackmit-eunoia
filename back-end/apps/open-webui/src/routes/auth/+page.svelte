<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { getBackendConfig } from '$lib/apis';
	import { getSessionUser, registerPublicUser } from '$lib/apis/auths';
	import { user, config } from '$lib/stores';
	import {
		getActingUserId,
		setActingUserId,
		installActingUidFetch
	} from '$lib/actingUser';
	import { toast } from 'svelte-sonner';
	import { copyToClipboard } from '$lib/utils';

	let uid = '';
	let loading = false;
	let regLoading = false;
	let showRegister = false;
	let configLoaded = false;
	/** 注册成功后展示的用户 ID（可复制） */
	let registeredUserId: string | null = null;

	onMount(async () => {
		installActingUidFetch();
		uid = getActingUserId();
		try {
			const bc = await getBackendConfig();
			const onboarding = Boolean(bc?.onboarding);
			const enableSignup = bc?.features?.enable_signup !== false;
			const disallow = Boolean(bc?.features?.disallow_user_registration);
			// X-Acting-Uid 部署下后端会返回 acting_user_id_header；旧数据里可能持久化了 enable_signup=false，
			// 仍应展示注册入口（是否允许第二个及以后用户由接口再校验 ENABLE_SIGNUP）。
			const actingUidStyle = Boolean(bc?.acting_user_id_header);
			showRegister =
				onboarding || (!disallow && (enableSignup || actingUidStyle));
		} catch {
			showRegister = true;
		} finally {
			configLoaded = true;
		}
	});

	const enterWithId = async (raw: string) => {
		const v = raw.trim();
		if (!v) {
			toast.error('请输入用户 ID（与后端用户表 id 一致）');
			return;
		}
		loading = true;
		try {
			setActingUserId(v);
			const sessionUser = await getSessionUser('');
			if (!sessionUser) {
				toast.error('无法获取会话：请确认该用户存在且请求头已生效');
				setActingUserId('');
				return;
			}
			await user.set(sessionUser);
			await config.set(await getBackendConfig());
			const redirect = $page.url.searchParams.get('redirect') || '/';
			await goto(redirect);
		} catch (e: unknown) {
			console.error(e);
			toast.error(
				typeof e === 'object' && e && 'detail' in e
					? String((e as { detail: string }).detail)
					: '登录失败'
			);
			setActingUserId('');
		} finally {
			loading = false;
		}
	};

	const continueWithUid = async () => {
		await enterWithId(uid);
	};

	const enterWithRegisteredId = async () => {
		if (!registeredUserId) return;
		uid = registeredUserId;
		await enterWithId(registeredUserId);
	};

	/** 一键注册：不要求用户名、密码、邮箱；成功后返回并展示 user-id */
	const quickRegister = async () => {
		registeredUserId = null;
		regLoading = true;
		try {
			const res = await registerPublicUser({});
			if (res?.id === undefined || res?.id === null) {
				toast.error('注册失败');
				return;
			}
			registeredUserId = typeof res.id === 'string' ? res.id : String(res.id);
			toast.success('注册成功，请保存您的用户 ID');
		} catch (e: unknown) {
			console.error(e);
			const msg =
				typeof e === 'string'
					? e
					: typeof e === 'object' && e && 'detail' in e
						? String((e as { detail: unknown }).detail)
						: '注册失败';
			toast.error(msg);
		} finally {
			regLoading = false;
		}
	};

	const copyRegisteredId = async () => {
		if (!registeredUserId) return;
		const ok = await copyToClipboard(registeredUserId);
		if (ok) {
			toast.success('已复制用户 ID');
		} else {
			toast.error('复制失败，请手动选择复制');
		}
	};

	const onRegisterClick = async () => {
		if (!configLoaded) return;
		if (!showRegister) {
			toast.error('当前未开放用户注册');
			return;
		}
		await quickRegister();
	};
</script>

<div class="flex min-h-screen w-full items-center justify-center bg-gray-50 dark:bg-gray-900 p-4">
	<div class="w-full max-w-md rounded-2xl border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-850 p-8 shadow-sm space-y-8">
		<div>
			<h1 class="text-xl font-semibold mb-2 text-gray-900 dark:text-gray-100">选择用户</h1>
			<p class="text-sm text-gray-600 dark:text-gray-400 mb-6">
				本部署使用请求头
				<code class="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">X-Acting-Uid</code>
				标识身份。可将用户 id 存入本机，由前端自动附加到 API 请求；或由网关注入。
			</p>
			<label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">用户 ID</label>
			<input
				class="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 mb-4 text-gray-900 dark:text-gray-100"
				bind:value={uid}
				placeholder="已有用户的 id（UUID）"
				autocomplete="username"
			/>
			<button
				class="w-full rounded-lg bg-black text-white dark:bg-white dark:text-black py-2.5 font-medium disabled:opacity-50"
				disabled={loading}
				on:click={continueWithUid}
			>
				{loading ? '验证中…' : '进入'}
			</button>

			<div class="mt-6 space-y-2">
				<h2 class="text-sm font-semibold text-gray-900 dark:text-gray-100">新用户注册</h2>
				<p class="text-xs text-gray-500 dark:text-gray-400">
					无需填写邮箱、密码或用户名。注册成功后将显示系统分配的唯一用户 ID，用于上方「进入」或网关注入
					<code class="text-xs">X-Acting-Uid</code>。首个注册用户为管理员。
				</p>
				<button
					type="button"
					class="w-full rounded-lg border border-gray-300 dark:border-gray-600 py-2.5 font-medium text-gray-900 dark:text-gray-100 disabled:opacity-50"
					disabled={regLoading || !configLoaded || (configLoaded && !showRegister)}
					on:click={onRegisterClick}
				>
					{regLoading ? '注册中…' : '一键注册'}
				</button>
				{#if configLoaded && !showRegister}
					<p class="text-xs text-amber-600 dark:text-amber-400">
						已关闭新用户注册（Disallow user registration）。若需开放，请在管理端关闭该选项或检查环境变量。
					</p>
				{/if}
			</div>

			{#if registeredUserId}
				<div
					class="mt-6 rounded-xl border border-emerald-200 dark:border-emerald-900 bg-emerald-50/80 dark:bg-emerald-950/40 p-4 space-y-3"
				>
					<p class="text-sm font-medium text-emerald-900 dark:text-emerald-100">您的唯一用户 ID</p>
					<code
						class="block w-full break-all rounded-lg bg-white dark:bg-gray-900 border border-emerald-100 dark:border-emerald-900 px-3 py-2 text-xs text-gray-900 dark:text-gray-100"
						>{registeredUserId}</code
					>
					<div class="flex flex-col gap-2 sm:flex-row">
						<button
							type="button"
							class="flex-1 rounded-lg bg-emerald-700 text-white dark:bg-emerald-600 py-2 text-sm font-medium"
							on:click={copyRegisteredId}
						>
							复制用户 ID
						</button>
						<button
							type="button"
							class="flex-1 rounded-lg border border-emerald-700 dark:border-emerald-500 text-emerald-900 dark:text-emerald-100 py-2 text-sm font-medium"
							disabled={loading}
							on:click={enterWithRegisteredId}
						>
							{loading ? '进入中…' : '进入应用'}
						</button>
					</div>
				</div>
			{/if}
		</div>

		<p class="text-xs text-gray-500 dark:text-gray-500">
			生产环境可在反向代理统一注入
			<code class="text-xs">X-Acting-Uid</code>，或使用
			<code class="text-xs">PUBLIC_ACTING_USER_ID</code>（可选）。
		</p>
	</div>
</div>
