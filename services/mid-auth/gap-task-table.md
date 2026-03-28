# Mid-auth 缺口接口冻结任务表（单一事实源）

更新时间：2026-03-23  
任务 ID：`gap-map-freeze`  
口径说明：仅纳入当前计划中明确的剩余补齐范围（OpenWebUI / VoceChat / Memos），并严格绑定既有路由分类与 tag，不新增跨类 router。

## 字段说明

- `method`：下游缺口操作方法
- `path`：下游缺口路径（占位符沿用 `{} `风格）
- `subdomain`：`OpenWebUI` / `VoceChat` / `Memos`
- `target_router_file`：mid-auth 目标落位文件（必须在现有文件内增量）
- `target_tag`：`main.py` 中既有 tag
- `client_method`：依赖/新增的下游 client 方法（命名冻结，供并行实现对齐）

## 统计（冻结）

- OpenWebUI：64
- VoceChat：12
- Memos：3
- Total：79

## OpenWebUI（64）

| id | method | path | subdomain | target_router_file | target_tag | client_method |
|---|---|---|---|---|---|---|
| OW-001 | DELETE | /api/v1/chats | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.delete_chats_bulk |
| OW-002 | GET | /api/v1/chats/all | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.list_chats_all |
| OW-003 | GET | /api/v1/chats/all/archived | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.list_chats_all_archived |
| OW-004 | GET | /api/v1/chats/all/db | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.list_chats_all_db |
| OW-005 | GET | /api/v1/chats/folder/{} | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.get_chats_folder |
| OW-006 | GET | /api/v1/chats/folder/{}/list | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.list_chats_folder |
| OW-007 | POST | /api/v1/chats/import | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.import_chats |
| OW-008 | GET | /api/v1/chats/list | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.list_chats |
| OW-009 | GET | /api/v1/chats/list/user/{} | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.list_chats_by_user |
| OW-010 | GET | /api/v1/chats/stats/export | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.export_chat_stats |
| OW-011 | GET | /api/v1/chats/stats/export/{} | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.export_chat_stats_by_id |
| OW-012 | GET | /api/v1/chats/stats/usage | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.get_chat_stats_usage |
| OW-013 | POST | /api/v1/chats/{}/clone | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.clone_chat |
| OW-014 | POST | /api/v1/chats/{}/clone/shared | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.clone_shared_chat |
| OW-015 | POST | /api/v1/chats/{}/folder | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.move_chat_to_folder |
| OW-016 | POST | /api/v1/chats/{}/messages/{} | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.update_chat_message |
| OW-017 | POST | /api/v1/chats/{}/messages/{}/event | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.create_chat_message_event |
| OW-018 | DELETE | /api/v1/chats/{}/share | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.delete_chat_share |
| OW-019 | POST | /api/v1/chats/{}/share | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.create_chat_share |
| OW-020 | DELETE | /api/v1/chats/{}/tags | OpenWebUI | services/mid-auth/app/api/routers/openwebui_chats.py | ai-workbench | openwebui_client.delete_chat_tag |
| OW-021 | GET | /api/v1/auths/admin/details | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_system.py | openwebui-admin | openwebui_client.get_auth_admin_details |
| OW-022 | POST | /api/v1/auths/add | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_system.py | openwebui-admin | openwebui_client.create_auth_user |
| OW-023 | POST | /api/v1/auths/update/profile | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_system.py | openwebui-admin | openwebui_client.update_auth_profile |
| OW-024 | POST | /api/v1/auths/update/timezone | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_system.py | openwebui-admin | openwebui_client.update_auth_timezone |
| OW-025 | GET | /api/version | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.get_version |
| OW-026 | GET | /api/version/updates | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.get_version_updates |
| OW-027 | GET | /api/changelog | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.get_changelog |
| OW-028 | GET | /health | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.get_health |
| OW-029 | GET | /health/db | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.get_health_db |
| OW-030 | GET | /manifest.json | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.get_manifest |
| OW-031 | GET | /api/config | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.get_config |
| OW-032 | GET | /api/usage | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.get_usage |
| OW-033 | GET | /api/tasks | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.list_tasks |
| OW-034 | GET | /api/tasks/chat/{} | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.get_task_chat |
| OW-035 | POST | /api/tasks/stop/{} | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.stop_task |
| OW-036 | GET | /api/v1/files | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_files.py | openwebui-admin-files | openwebui_client.list_files |
| OW-037 | DELETE | /api/v1/files/all | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_files.py | openwebui-admin-files | openwebui_client.delete_files_all |
| OW-038 | GET | /api/v1/files/search | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_files.py | openwebui-admin-files | openwebui_client.search_files |
| OW-039 | DELETE | /api/v1/files/{} | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_files.py | openwebui-admin-files | openwebui_client.delete_file |
| OW-040 | GET | /api/v1/files/{} | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_files.py | openwebui-admin-files | openwebui_client.get_file |
| OW-041 | GET | /api/v1/files/{}/content | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_files.py | openwebui-admin-files | openwebui_client.get_file_content |
| OW-042 | GET | /api/v1/files/{}/content/html | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_files.py | openwebui-admin-files | openwebui_client.get_file_content_html |
| OW-043 | GET | /api/v1/files/{}/content/{} | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_files.py | openwebui-admin-files | openwebui_client.get_file_content_chunk |
| OW-044 | GET | /api/v1/files/{}/data/content | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_files.py | openwebui-admin-files | openwebui_client.get_file_data_content |
| OW-045 | POST | /api/v1/files/{}/data/content/update | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_files.py | openwebui-admin-files | openwebui_client.update_file_data_content |
| OW-046 | GET | /api/v1/files/{}/process/status | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_files.py | openwebui-admin-files | openwebui_client.get_file_process_status |
| OW-047 | GET | /api/v1/audio/config | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.get_audio_config |
| OW-048 | POST | /api/v1/audio/config/update | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.update_audio_config |
| OW-049 | GET | /api/v1/audio/models | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.list_audio_models |
| OW-050 | POST | /api/v1/audio/speech | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.create_audio_speech |
| OW-051 | POST | /api/v1/audio/transcriptions | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.create_audio_transcription |
| OW-052 | GET | /api/v1/audio/voices | OpenWebUI | services/mid-auth/app/api/routers/openwebui_me.py | ai-workbench | openwebui_client.list_audio_voices |
| OW-053 | GET | /api/v1/prompts/id/{}/history | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_prompts_tools.py | openwebui-admin-prompts-tools | openwebui_client.list_prompt_history |
| OW-054 | GET | /api/v1/prompts/id/{}/history/diff | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_prompts_tools.py | openwebui-admin-prompts-tools | openwebui_client.get_prompt_history_diff |
| OW-055 | GET | /api/v1/prompts/id/{}/history/{} | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_prompts_tools.py | openwebui-admin-prompts-tools | openwebui_client.get_prompt_history_item |
| OW-056 | DELETE | /api/v1/prompts/id/{}/history/{} | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_prompts_tools.py | openwebui-admin-prompts-tools | openwebui_client.delete_prompt_history_item |
| OW-057 | GET | /api/v1/knowledge/{}/export | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_knowledge.py | openwebui-admin-knowledge | openwebui_client.export_knowledge |
| OW-058 | POST | /api/v1/knowledge/{}/file/remove | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_knowledge.py | openwebui-admin-knowledge | openwebui_client.remove_knowledge_file |
| OW-059 | POST | /api/v1/knowledge/{}/file/update | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_knowledge.py | openwebui-admin-knowledge | openwebui_client.update_knowledge_file |
| OW-060 | GET | /api/models | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_models.py | openwebui-admin | openwebui_client.list_models_legacy |
| OW-061 | GET | /api/models/base | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_models.py | openwebui-admin | openwebui_client.list_models_base_legacy |
| OW-062 | GET | /api/v1/models/export | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_models.py | openwebui-admin | openwebui_client.export_models |
| OW-063 | POST | /api/v1/models/import | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_models.py | openwebui-admin | openwebui_client.import_models |
| OW-064 | POST | /api/v1/models/model/access/update | OpenWebUI | services/mid-auth/app/api/routers/openwebui_admin_models.py | openwebui-admin | openwebui_client.update_model_access |

## VoceChat（12）

| id | method | path | subdomain | target_router_file | target_tag | client_method |
|---|---|---|---|---|---|---|
| VC-001 | POST | /admin/system/create_admin | VoceChat | services/mid-auth/app/api/routers/admin_vocechat.py | admin-vocechat | vocechat_client.create_admin |
| VC-002 | GET | /admin/system/organization | VoceChat | services/mid-auth/app/api/routers/admin_vocechat.py | admin-vocechat | vocechat_client.get_organization |
| VC-003 | POST | /admin/system/organization | VoceChat | services/mid-auth/app/api/routers/admin_vocechat.py | admin-vocechat | vocechat_client.update_organization |
| VC-004 | POST | /admin/system/organization/logo | VoceChat | services/mid-auth/app/api/routers/admin_vocechat.py | admin-vocechat | vocechat_client.update_organization_logo |
| VC-005 | GET | /admin/system/third_party_secret | VoceChat | services/mid-auth/app/api/routers/admin_vocechat.py | admin-vocechat | vocechat_client.get_third_party_secret |
| VC-006 | POST | /admin/system/third_party_secret | VoceChat | services/mid-auth/app/api/routers/admin_vocechat.py | admin-vocechat | vocechat_client.update_third_party_secret |
| VC-007 | GET | /admin/system/version | VoceChat | services/mid-auth/app/api/routers/admin_vocechat.py | admin-vocechat | vocechat_client.get_system_version |
| VC-009 | GET | /resource/group_avatar | VoceChat | services/mid-auth/app/api/routers/chat_resources.py | chat-resources | vocechat_client.get_group_avatar_resource |
| VC-010 | GET | /resource/organization/logo | VoceChat | services/mid-auth/app/api/routers/chat_resources.py | chat-resources | vocechat_client.get_organization_logo_resource |
| VC-011 | GET | /favorite/attachment/{}/{}/{} | VoceChat | services/mid-auth/app/api/routers/favorites.py | favorites | vocechat_client.get_favorite_attachment |
| VC-012 | POST | /group/{}/avatar | VoceChat | services/mid-auth/app/api/routers/groups.py | groups | vocechat_client.update_group_avatar |

## Memos（3）

| id | method | path | subdomain | target_router_file | target_tag | client_method |
|---|---|---|---|---|---|---|
| MM-001 | GET | /api/v1/instance/{}/* | Memos | services/mid-auth/app/api/routers/me_memos.py | library | memos_client.get_instance_dynamic_setting |
| MM-002 | PATCH | /api/v1/instance/{}/* | Memos | services/mid-auth/app/api/routers/me_memos.py | library | memos_client.patch_instance_dynamic_setting |
| MM-003 | DELETE | /api/v1/memos/{}/reactions/{} | Memos | services/mid-auth/app/api/routers/posts.py | posts | memos_client.delete_memo_reaction |

## 任务分发规则（并行执行约束）

- 以本文件为唯一任务源；并行 agent 仅领取 `id` 区间，不自行增删分类。
- 每个接口实现必须同时落地：`router + client + schema/service（按需） + smoke test`。
- 若实现时发现下游接口已废弃/不可达：保留 `id`，在 PR 中标注 `defer:<reason>`，不得直接删除行。
- 任何新增接口均不得修改 `target_tag` 与 `target_router_file` 所属分类。
