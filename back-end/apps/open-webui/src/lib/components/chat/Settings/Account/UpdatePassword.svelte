<script lang="ts">
	import { getContext } from 'svelte';
	const i18n = getContext('i18n');
</script>

<p class="text-sm text-gray-500 dark:text-gray-400">
	{$i18n.t('Password login has been removed in this deployment. Use X-Acting-Uid / acting user id instead.')}
</p>
