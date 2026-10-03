# 托管数据备份与恢复

工具用于当前网站数据卷布局：主库`filemate.db`、匿名`users/u_<32位hex>/filemate.db`、各自`inbox/`和`archive/`及有效的`identity.secret`。入口是`python -m filemate.operations.backup`；没有公网恢复API，不启动服务，不改迁移。

覆盖全部已识别分库、附件、空目录及身份密钥。SQLite使用[官方备份接口](https://www.sqlite.org/backup.html)，已提交WAL合并到目标库，WAL/SHM不作为恢复文件复制。源目录有未知布局、外部绝对文件引用、坏库、外键损坏、必要迁移缺失、无效匿名密钥、链接或重解析点时拒绝创建不完整快照。

## 一致性与配置

每个库可通过SQLite接口取得快照，但附件和多个分库不属于同一事务。完整备份必须先停止API和所有写入者，在整个预览/创建期间保持停写；`--quiesced`是管理员的显式声明，工具不擅自终止其他进程。创建前后核对指纹，数据变化时保留失败目录且不标记成功。

无已提交WAL时，预览用不可变只读连接避免新建辅助文件；有已提交WAL时要求已有共享索引。缺少SHM或仍有回滚日志时，先由原应用完成数据库恢复和正常关闭，再预览；不要手工删除WAL。[SQLite只读WAL说明](https://www.sqlite.org/wal.html#read_only_databases)解释了辅助文件要求。

`FILEMATE_IDENTITY_SECRET`环境值优先于磁盘，与服务一致；有效值保存到快照的私有`identity.secret`，不会打印密钥。恢复启用时同名环境配置必须对应原值，否则旧Cookie失效。供应商API密钥、`.env`和部署配置不进入数据快照，由原部署的秘密管理维护。

备份不是加密包。POSIX新目录700、新文件600；Windows需父目录的管理员私有ACL。清单、数据库和附件可能包含私人资料，必须存放于受限目录/加密存储，不提交Git或放入Web静态目录。校验和检测损坏，不能对抗可同时改写清单的攻击者。

## 本机命令

先停止自己负责的API，准备已存在的私有备份父目录：

```powershell
uv run python -m filemate.operations.backup plan --data-dir <托管数据根目录>
uv run python -m filemate.operations.backup create --data-dir <同一根目录> --out <尚不存在的新备份目录> --confirm <预览confirmation> --quiesced
uv run python -m filemate.operations.backup verify --backup <备份目录>
uv run python -m filemate.operations.backup restore-plan --backup <备份目录> --target <尚不存在的新恢复目录>
uv run python -m filemate.operations.backup restore --backup <备份目录> --target <同一新恢复目录> --confirm <恢复预览confirmation>
```

输出JSON摘要，正常退出码0，拒绝或失败为1。旧预览在源变化后失效。目标必须不存在，输入/输出不能嵌套，恢复目录不能嵌入现役数据；重复确认不覆盖。失败保留自己新建的目录，缺少有效清单或校验失败的目录不能启用。

## Compose数据卷

使用包含工具的已验证API镜像。进入`deploy/`，准备主机私有父目录`/srv/filemate-backups`，停止API后使用一次性容器：

```bash
docker compose --env-file .env.production stop api
docker compose --env-file .env.production run --rm -T --no-deps -v /srv/filemate-backups:/backup api python -m filemate.operations.backup plan --data-dir /data
docker compose --env-file .env.production run --rm -T --no-deps -v /srv/filemate-backups:/backup api python -m filemate.operations.backup create --data-dir /data --out /backup/<新快照名> --confirm <预览confirmation> --quiesced
docker compose --env-file .env.production run --rm -T --no-deps -v /srv/filemate-backups:/backup api python -m filemate.operations.backup verify --backup /backup/<新快照名>
docker compose --env-file .env.production start api
```

创建失败时不继续发布。先核对备份校验及原服务正常启动。异地保存、每日7份/每周4份保留及服务器调度尚需部署接线；工具不自动删除历史版本。

## 暂存恢复与启用

恢复只创建新目录并核对文件哈希、数据库完整性/外键和各表记录数，返回`activated:false`。Source/执行记录的绝对路径保留，不静默重写。**仅在原平台、原逻辑路径启用**：容器演练把新目录挂载为原`/data`，使用独立端口及相同配置；不要直接将暂存目录作为另一根路径启动并执行文件操作。

启用前停止旧写入者，保留原卷，再把验证的新卷挂载到同一逻辑路径。核对健康、原Cookie、资料正文、附件、会话、隔离及授权，再开放写入。异常时关闭恢复实例、改回原卷，不覆盖原库、不删除原卷、不换身份密钥。工具不执行卷替换或自动发布。

当前默认本地归档可能位于数据根目录外。这类桌面文件和跨平台路径迁移尚不支持，数据库绝对引用使完整创建被拒绝；须后续处理明确授权的外部目录，不能遗漏后称为完整桌面备份。

## 可复跑演练

```powershell
uv run pytest filemate/tests/test_backup.py -q
uv run python scripts/acceptance/backup_restore.py --out _working/<新演练目录>
```

脚本建立三个合成库，两个实际匿名HTTP访客导入原创TXT、创建会话；只停止自有进程，保留原合成目录，在同一逻辑路径重启恢复实例。检查原Cookie、正文/会话、跨访客404、重复确认和损坏快照拒绝；无私人库、线上写入或外部模型调用。见[阶段交付](OPERATIONS_BACKUP_DELIVERY_2026-10-03.md)。
