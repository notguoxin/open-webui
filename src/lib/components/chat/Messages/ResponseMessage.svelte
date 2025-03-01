<script lang="ts">
	import { toast } from 'svelte-sonner';
	import dayjs from 'dayjs';

	import { createEventDispatcher } from 'svelte';
	import { onMount, tick, getContext } from 'svelte';

	const i18n = getContext<Writable<i18nType>>('i18n');

	const dispatch = createEventDispatcher();

	import { config, models, settings, user } from '../../../../lib/stores';
	import { imageGenerations } from '../../../../lib/apis/images';
	import {
		copyToClipboard as _copyToClipboard,
		approximateToHumanReadable,
		sanitizeResponseContent,
		createMessagesList
	} from '../../../../lib/utils';
	import { WEBUI_BASE_URL } from '../../../../lib/constants';

	import Name from './Name.svelte';
	import ProfileImage from './ProfileImage.svelte';
	import Skeleton from './Skeleton.svelte';
	import Image from '../../../../lib/components/common/Image.svelte';
	import Tooltip from '../../../../lib/components/common/Tooltip.svelte';
	import Spinner from '../../../../lib/components/common/Spinner.svelte';
	import Sparkles from '../../../../lib/components/icons/Sparkles.svelte';
	import Error from './Error.svelte';
	import Citations from './Citations.svelte';
	import CodeExecutions from './CodeExecutions.svelte';

	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import ContentRenderer from './ContentRenderer.svelte';
	import { getChatById } from '../../../../lib/apis/chats';

	interface MessageType {
		id: string;
		model: string;
		content: string;
		files?: { type: string; url: string }[];
		timestamp: number;
		role: string;
		statusHistory?: {
			done: boolean;
			action: string;
			description: string;
			urls?: string[];
			query?: string;
		}[];
		status?: {
			done: boolean;
			action: string;
			description: string;
			urls?: string[];
			query?: string;
		};
		done: boolean;
		error?: boolean | { content: string };
		sources?: string[];
		code_executions?: {
			uuid: string;
			name: string;
			code: string;
			language?: string;
			result?: {
				error?: string;
				output?: string;
				files?: { name: string; url: string }[];
			};
		}[];
		info?: {
			openai?: boolean;
			prompt_tokens?: number;
			completion_tokens?: number;
			total_tokens?: number;
			eval_count?: number;
			eval_duration?: number;
			prompt_eval_count?: number;
			prompt_eval_duration?: number;
			total_duration?: number;
			load_duration?: number;
			usage?: unknown;
		};
		annotation?: { type: string; rating: number };
	}

	export let chatId = '';
	export let history;
	export let messageId;

	let message: MessageType = JSON.parse(JSON.stringify(history.messages[messageId]));
	$: if (history.messages) {
		if (JSON.stringify(message) !== JSON.stringify(history.messages[messageId])) {
			message = JSON.parse(JSON.stringify(history.messages[messageId]));
		}
	}

	export let siblings;

	export let showPreviousMessage: Function;
	export let showNextMessage: Function;

	export let updateChat: Function;
	export let editMessage: Function;
	export let saveMessage: Function;
	export let actionMessage: Function;

	export let submitMessage: Function;
	export let continueResponse: Function;
	export let regenerateResponse: Function;

	export let addMessages: Function;

	export let isLastMessage = true;
	export let readOnly = false;

	let model = null;
	$: model = $models.find((m) => m.id === message.model);

	let edit = false;
	let editedContent = '';
	let editTextAreaElement: HTMLTextAreaElement;

	let loadingSpeech = false;
	let generatingImage = false;

	const copyToClipboard = async (text) => {
		const res = await _copyToClipboard(text);
		if (res) {
			toast.success($i18n.t('Copying to clipboard was successful!'));
		}
	};

	const editMessageHandler = async () => {
		edit = true;
		editedContent = message.content;

		await tick();

		editTextAreaElement.style.height = '';
		editTextAreaElement.style.height = `${editTextAreaElement.scrollHeight}px`;
	};

	const editMessageConfirmHandler = async () => {
		editMessage(message.id, editedContent ? editedContent : '', false);

		edit = false;
		editedContent = '';

		await tick();
	};

	const saveAsCopyHandler = async () => {
		editMessage(message.id, editedContent ? editedContent : '');

		edit = false;
		editedContent = '';

		await tick();
	};

	const cancelEditMessage = async () => {
		edit = false;
		editedContent = '';
		await tick();
	};

	const generateImage = async (message: MessageType) => {
		generatingImage = true;
		const res = await imageGenerations(localStorage.token, message.content).catch((error) => {
			toast.error(error);
		});
		console.log(res);

		if (res) {
			const files = res.map((image) => ({
				type: 'image',
				url: `${image.url}`
			}));

			saveMessage(message.id, {
				...message,
				files: files
			});
		}

		generatingImage = false;
	};

	let feedbackLoading = false;

	const feedbackHandler = async (rating: number | null = null, details: object | null = null) => {
		feedbackLoading = true;
		console.log('Feedback', rating, details);

		const updatedMessage = {
			...message,
			annotation: {
				...(message?.annotation ?? {}),
				...(rating !== null ? { rating: rating } : {}),
				...(details ? details : {})
			}
		};

		const chat = await getChatById(localStorage.token, chatId).catch((error) => {
			toast.error(error);
		});
		if (!chat) {
			return;
		}

		const messages = createMessagesList(history, message.id);

		let feedbackItem = {
			type: 'rating',
			data: {
				...(updatedMessage?.annotation ? updatedMessage.annotation : {}),
				model_id: message?.selectedModelId ?? message.model,
				...(history.messages[message.parentId].childrenIds.length > 1
					? {
							sibling_model_ids: history.messages[message.parentId].childrenIds
								.filter((id) => id !== message.id)
								.map((id) => history.messages[id]?.selectedModelId ?? history.messages[id].model)
						}
					: {})
			},
			meta: {
				model_id: message.model,
				message_id: message.id,
				message_index: messages.length,
				chat_id: chatId
			},
			snapshot: {
				chat: chat
			}
		};

		const baseModels = [
			feedbackItem.data.model_id,
			...(feedbackItem.data.sibling_model_ids ?? [])
		].reduce((acc, modelId) => {
			const model = $models.find((m) => m.id === modelId);
			if (model) {
				acc[model.id] = model?.info?.base_model_id ?? null;
			} else {
				// Log or handle cases where corresponding model is not found
				console.warn(`Model with ID ${modelId} not found`);
			}
			return acc;
		}, {});
		feedbackItem.meta.base_models = baseModels;

		console.log(updatedMessage);
		saveMessage(message.id, updatedMessage);

		await tick();

		feedbackLoading = false;
	};

	$: if (!edit) {
		(async () => {
			await tick();
		})();
	}

	onMount(async () => {
		// console.log('ResponseMessage mounted');

		await tick();
	});
</script>

{#key message.id}
	<div
		class=" flex w-full message-{message.id}"
		id="message-{message.id}"
		dir={$settings.chatDirection}
	>
		<div class={`flex-shrink-0 ${($settings?.chatDirection ?? 'LTR') === 'LTR' ? 'mr-3' : 'ml-3'}`}>
			<ProfileImage
				src={model?.info?.meta?.profile_image_url ??
					($i18n.language === 'dg-DG' ? `/doge.png` : `${WEBUI_BASE_URL}/static/favicon.png`)}
				className={'size-8'}
			/>
		</div>

		<div class="flex-auto w-0 pl-1">
			<Name>
				<Tooltip content={model?.name ?? message.model} placement="top-start">
					<span class="line-clamp-1">
						{model?.name ?? message.model}
					</span>
				</Tooltip>

				{#if message.timestamp}
					<span
						class=" self-center shrink-0 translate-y-0.5 invisible group-hover:visible text-gray-400 text-xs font-medium uppercase ml-0.5 -mt-0.5"
					>
						{dayjs(message.timestamp * 1000).format($i18n.t('h:mm a'))}
					</span>
				{/if}
			</Name>

			<div>
				{#if message?.files && message.files?.filter((f) => f.type === 'image').length > 0}
					<div class="my-2.5 w-full flex overflow-x-auto gap-2 flex-wrap">
						{#each message.files as file}
							<div>
								{#if file.type === 'image'}
									<Image src={file.url} alt={message.content} />
								{/if}
							</div>
						{/each}
					</div>
				{/if}

				<div class="chat-{message.role} w-full min-w-full markdown-prose">
					<div>
						{#if (message?.statusHistory ?? [...(message?.status ? [message?.status] : [])]).length > 0}
							{@const status = (
								message?.statusHistory ?? [...(message?.status ? [message?.status] : [])]
							).at(-1)}
							{#if !status?.hidden}
								<div class="status-description flex items-center gap-2 py-0.5">
									{#if status?.done === false}
										<div class="">
											<Spinner className="size-4" />
										</div>
									{/if}

									{#if status?.action === 'knowledge_search'}
										<div class="flex flex-col justify-center -space-y-0.5">
											<div
												class="{status?.done === false
													? 'shimmer'
													: ''} text-gray-500 dark:text-gray-500 text-base line-clamp-1 text-wrap"
											>
												{$i18n.t(`Searching Knowledge for "{{searchQuery}}"`, {
													searchQuery: status.query
												})}
											</div>
										</div>
									{:else}
										<div class="flex flex-col justify-center -space-y-0.5">
											<div
												class="{status?.done === false
													? 'shimmer'
													: ''} text-gray-500 dark:text-gray-500 text-base line-clamp-1 text-wrap"
											>
												<!-- $i18n.t(`Searching "{{searchQuery}}"`) -->
												{#if status?.description.includes('{{searchQuery}}')}
													{$i18n.t(status?.description, {
														searchQuery: status?.query
													})}
												{:else if status?.description === 'No search query generated'}
													{$i18n.t('No search query generated')}
												{:else if status?.description === 'Generating search query'}
													{$i18n.t('Generating search query')}
												{:else}
													{status?.description}
												{/if}
											</div>
										</div>
									{/if}
								</div>
							{/if}
						{/if}

						{#if edit === true}
							<div class="w-full bg-gray-50 dark:bg-gray-800 rounded-3xl px-5 py-3 my-2">
								<textarea
									id="message-edit-{message.id}"
									bind:this={editTextAreaElement}
									class=" bg-transparent outline-none w-full resize-none"
									bind:value={editedContent}
									on:input={(e) => {
										e.target.style.height = '';
										e.target.style.height = `${e.target.scrollHeight}px`;
									}}
									on:keydown={(e) => {
										if (e.key === 'Escape') {
											document.getElementById('close-edit-message-button')?.click();
										}

										const isCmdOrCtrlPressed = e.metaKey || e.ctrlKey;
										const isEnterPressed = e.key === 'Enter';

										if (isCmdOrCtrlPressed && isEnterPressed) {
											document.getElementById('confirm-edit-message-button')?.click();
										}
									}}
								/>

								<div class=" mt-2 mb-1 flex justify-between text-sm font-medium">
									<div>
										<button
											id="save-new-message-button"
											class=" px-4 py-2 bg-gray-50 hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700 border dark:border-gray-700 text-gray-700 dark:text-gray-200 transition rounded-3xl"
											on:click={() => {
												saveAsCopyHandler();
											}}
										>
											{$i18n.t('Save As Copy')}
										</button>
									</div>

									<div class="flex space-x-1.5">
										<button
											id="close-edit-message-button"
											class="px-4 py-2 bg-white dark:bg-gray-900 hover:bg-gray-100 text-gray-800 dark:text-gray-100 transition rounded-3xl"
											on:click={() => {
												cancelEditMessage();
											}}
										>
											{$i18n.t('Cancel')}
										</button>

										<button
											id="confirm-edit-message-button"
											class=" px-4 py-2 bg-gray-900 dark:bg-white hover:bg-gray-850 text-gray-100 dark:text-gray-800 transition rounded-3xl"
											on:click={() => {
												editMessageConfirmHandler();
											}}
										>
											{$i18n.t('Save')}
										</button>
									</div>
								</div>
							</div>
						{:else}
							<div class="w-full flex flex-col relative" id="response-content-container">
								{#if message.content === '' && !message.error}
									<Skeleton />
								{:else if message.content && message.error !== true}
									<!-- always show message contents even if there's an error -->
									<!-- unless message.error === true which is legacy error handling, where the error message is stored in message.content -->
									<ContentRenderer
										id={message.id}
										{history}
										content={message.content}
										sources={message.sources}
										save={!readOnly}
										{model}
										onSourceClick={(e) => {
											console.log(e);
											const sourceButton = document.getElementById(`source-${e}`);

											if (sourceButton) {
												sourceButton.click();
											}
										}}
										onAddMessages={({ modelId, parentId, messages }) => {
											addMessages({ modelId, parentId, messages });
										}}
										on:update={(e) => {
											const { raw, oldContent, newContent } = e.detail;

											history.messages[message.id].content = history.messages[
												message.id
											].content.replace(raw, raw.replace(oldContent, newContent));

											updateChat();
										}}
										on:select={(e) => {
											const { type, content } = e.detail;

											if (type === 'explain') {
												submitMessage(
													message.id,
													`Explain this section to me in more detail\n\n\`\`\`\n${content}\n\`\`\``
												);
											} else if (type === 'ask') {
												const input = e.detail?.input ?? '';
												submitMessage(message.id, `\`\`\`\n${content}\n\`\`\`\n${input}`);
											}
										}}
									/>
								{/if}

								{#if message?.error}
									<Error content={message?.error?.content ?? message.content} />
								{/if}

								{#if (message?.sources || message?.citations) && (model?.info?.meta?.capabilities?.citations ?? true)}
									<Citations sources={message?.sources ?? message?.citations} />
								{/if}

								{#if message.code_executions}
									<CodeExecutions codeExecutions={message.code_executions} />
								{/if}
							</div>
						{/if}
					</div>
				</div>

				{#if !edit}
					{#if message.done || siblings.length > 1}
						<div
							class=" flex justify-start overflow-x-auto buttons text-gray-600 dark:text-gray-500 mt-0.5"
						>
							{#if siblings.length > 1}
								<div class="flex self-center min-w-fit" dir="ltr">
									<button
										class="self-center p-1 hover:bg-black/5 dark:hover:bg-white/5 dark:hover:text-white hover:text-black rounded-md transition"
										on:click={() => {
											showPreviousMessage(message);
										}}
									>
										<svg
											xmlns="http://www.w3.org/2000/svg"
											fill="none"
											viewBox="0 0 24 24"
											stroke="currentColor"
											stroke-width="2.5"
											class="size-3.5"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M15.75 19.5 8.25 12l7.5-7.5"
											/>
										</svg>
									</button>

									<div
										class="text-sm tracking-widest font-semibold self-center dark:text-gray-100 min-w-fit"
									>
										{siblings.indexOf(message.id) + 1}/{siblings.length}
									</div>

									<button
										class="self-center p-1 hover:bg-black/5 dark:hover:bg-white/5 dark:hover:text-white hover:text-black rounded-md transition"
										on:click={() => {
											showNextMessage(message);
										}}
									>
										<svg
											xmlns="http://www.w3.org/2000/svg"
											fill="none"
											viewBox="0 0 24 24"
											stroke="currentColor"
											stroke-width="2.5"
											class="size-3.5"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="m8.25 4.5 7.5 7.5-7.5 7.5"
											/>
										</svg>
									</button>
								</div>
							{/if}

							{#if message.done}
								{#if !readOnly}
									{#if $user.role === 'user' ? ($user?.permissions?.chat?.edit ?? true) : true}
										<Tooltip content={$i18n.t('Edit')} placement="bottom">
											<button
												class="{isLastMessage
													? 'visible'
													: 'invisible group-hover:visible'} p-1.5 hover:bg-black/5 dark:hover:bg-white/5 rounded-lg dark:hover:text-white hover:text-black transition"
												on:click={() => {
													editMessageHandler();
												}}
											>
												<svg
													xmlns="http://www.w3.org/2000/svg"
													fill="none"
													viewBox="0 0 24 24"
													stroke-width="2.3"
													stroke="currentColor"
													class="w-4 h-4"
												>
													<path
														stroke-linecap="round"
														stroke-linejoin="round"
														d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L6.832 19.82a4.5 4.5 0 01-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 011.13-1.897L16.863 4.487zm0 0L19.5 7.125"
													/>
												</svg>
											</button>
										</Tooltip>
									{/if}
								{/if}

								<Tooltip content={$i18n.t('Copy')} placement="bottom">
									<button
										class="{isLastMessage
											? 'visible'
											: 'invisible group-hover:visible'} p-1.5 hover:bg-black/5 dark:hover:bg-white/5 rounded-lg dark:hover:text-white hover:text-black transition copy-response-button"
										on:click={() => {
											copyToClipboard(message.content);
										}}
									>
										<svg
											xmlns="http://www.w3.org/2000/svg"
											fill="none"
											viewBox="0 0 24 24"
											stroke-width="2.3"
											stroke="currentColor"
											class="w-4 h-4"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184"
											/>
										</svg>
									</button>
								</Tooltip>

								{#if message.usage}
									<Tooltip
										content={message.usage
											? `<pre>${sanitizeResponseContent(
													JSON.stringify(message.usage, null, 2)
														.replace(/"([^(")"]+)":/g, '$1:')
														.slice(1, -1)
														.split('\n')
														.map((line) => line.slice(2))
														.map((line) => (line.endsWith(',') ? line.slice(0, -1) : line))
														.join('\n')
												)}</pre>`
											: ''}
										placement="bottom"
									>
										<button
											class=" {isLastMessage
												? 'visible'
												: 'invisible group-hover:visible'} p-1.5 hover:bg-black/5 dark:hover:bg-white/5 rounded-lg dark:hover:text-white hover:text-black transition whitespace-pre-wrap"
											on:click={() => {
												console.log(message);
											}}
											id="info-{message.id}"
										>
											<svg
												xmlns="http://www.w3.org/2000/svg"
												fill="none"
												viewBox="0 0 24 24"
												stroke-width="2.3"
												stroke="currentColor"
												class="w-4 h-4"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z"
												/>
											</svg>
										</button>
									</Tooltip>
								{/if}

								{#if !readOnly}
									{#if isLastMessage}
										<Tooltip content={$i18n.t('Continue Response')} placement="bottom">
											<button
												type="button"
												id="continue-response-button"
												class="{isLastMessage
													? 'visible'
													: 'invisible group-hover:visible'} p-1.5 hover:bg-black/5 dark:hover:bg-white/5 rounded-lg dark:hover:text-white hover:text-black transition regenerate-response-button"
												on:click={() => {
													continueResponse();
												}}
											>
												<svg
													xmlns="http://www.w3.org/2000/svg"
													fill="none"
													viewBox="0 0 24 24"
													stroke-width="2.3"
													stroke="currentColor"
													class="w-4 h-4"
												>
													<path
														stroke-linecap="round"
														stroke-linejoin="round"
														d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
													/>
													<path
														stroke-linecap="round"
														stroke-linejoin="round"
														d="M15.91 11.672a.375.375 0 0 1 0 .656l-5.603 3.113a.375.375 0 0 1-.557-.328V8.887c0-.286.307-.466.557-.327l5.603 3.112Z"
													/>
												</svg>
											</button>
										</Tooltip>
									{/if}

									<Tooltip content={$i18n.t('Regenerate')} placement="bottom">
										<button
											type="button"
											class="{isLastMessage
												? 'visible'
												: 'invisible group-hover:visible'} p-1.5 hover:bg-black/5 dark:hover:bg-white/5 rounded-lg dark:hover:text-white hover:text-black transition regenerate-response-button"
											on:click={() => {
												regenerateResponse(message);

												(model?.actions ?? []).forEach((action) => {
													dispatch('action', {
														id: action.id,
														event: {
															id: 'regenerate-response',
															data: {
																messageId: message.id
															}
														}
													});
												});
											}}
										>
											<svg
												xmlns="http://www.w3.org/2000/svg"
												fill="none"
												viewBox="0 0 24 24"
												stroke-width="2.3"
												stroke="currentColor"
												class="w-4 h-4"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99"
												/>
											</svg>
										</button>
									</Tooltip>

									{#if isLastMessage}
										{#each model?.actions ?? [] as action}
											<Tooltip content={action.name} placement="bottom">
												<button
													type="button"
													class="{isLastMessage
														? 'visible'
														: 'invisible group-hover:visible'} p-1.5 hover:bg-black/5 dark:hover:bg-white/5 rounded-lg dark:hover:text-white hover:text-black transition regenerate-response-button"
													on:click={() => {
														actionMessage(action.id, message);
													}}
												>
													{#if action.icon_url}
														<img
															src={action.icon_url}
															class="w-4 h-4 {action.icon_url.includes('svg')
																? 'dark:invert-[80%]'
																: ''}"
															style="fill: currentColor;"
															alt={action.name}
														/>
													{:else}
														<Sparkles strokeWidth="2.1" className="size-4" />
													{/if}
												</button>
											</Tooltip>
										{/each}
									{/if}
								{/if}
							{/if}
						</div>
					{/if}
				{/if}
			</div>
		</div>
	</div>
{/key}

<style>
	.buttons::-webkit-scrollbar {
		display: none; /* for Chrome, Safari and Opera */
	}

	.buttons {
		-ms-overflow-style: none; /* IE and Edge */
		scrollbar-width: none; /* Firefox */
	}

	@keyframes shimmer {
		0% {
			background-position: 200% 0;
		}
		100% {
			background-position: -200% 0;
		}
	}

	.shimmer {
		background: linear-gradient(90deg, #9a9b9e 25%, #2a2929 50%, #9a9b9e 75%);
		background-size: 200% 100%;
		background-clip: text;
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		animation: shimmer 4s linear infinite;
		color: #818286; /* Fallback color */
	}

	:global(.dark) .shimmer {
		background: linear-gradient(90deg, #818286 25%, #eae5e5 50%, #818286 75%);
		background-size: 200% 100%;
		background-clip: text;
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		animation: shimmer 4s linear infinite;
		color: #a1a3a7; /* Darker fallback color for dark mode */
	}

	@keyframes smoothFadeIn {
		0% {
			opacity: 0;
			transform: translateY(-10px);
		}
		100% {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.status-description {
		animation: smoothFadeIn 0.2s forwards;
	}
</style>
