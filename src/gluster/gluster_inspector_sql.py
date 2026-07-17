# src/gluster/gluster_inspector_sql.py
"""
Модуль генерации диагностического отчета по тому Gluster (Volume-Inspector).
Использует прямое подключение psycopg2 и VIEW-таблицы для денормализованных данных.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os
from datetime import datetime
import html

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import psycopg2
from psycopg2.extras import RealDictCursor


def _safe_text(value):
    """Экранирует HTML-спецсимволы для безопасного вывода."""
    if value is None:
        return "—"
    return html.escape(str(value))


def get_gluster_volume_report(db_name: str, volume_id: str) -> dict:
    """
    Возвращает словарь с текстовым отчетом по тому Gluster.
    
    Args:
        db_name: Имя базы данных (дампа)
        volume_id: UUID тома
        
    Returns:
        Словарь с ключами: report_text, nav_data, error
    """
    vid_search = str(volume_id).strip().lower()
    
    conn_params = {
        "dbname": db_name,
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
    }

    try:
        with psycopg2.connect(**conn_params) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                now_naive = datetime.now().replace(tzinfo=None)

                # 1. Основная информация (через VIEW для получения имени кластера)
                cur.execute("""
                    SELECT 
                        v.vol_name,
                        v.cluster_name,
                        v.vol_type,
                        v.status,
                        v.replica_count,
                        v.disperse_count,
                        v.stripe_count,
                        v.snapshot_count,
                        vd.total_space,
                        vd.used_space,
                        vd.free_space
                    FROM gluster_volumes_view v
                    LEFT JOIN gluster_volume_details vd ON v.id::text = vd.volume_id::text
                    WHERE v.id::text = %s
                    LIMIT 1
                """, (vid_search,))
                
                vol_row = cur.fetchone()
                if not vol_row:
                    return {"error": "Том не найден.", "report_text": "", "nav_data": {}}

                vol_name = vol_row['vol_name'] or "(без имени)"
                cluster_name = vol_row['cluster_name'] or "—"
                status = vol_row['status'] or "Unknown"
                vol_type = vol_row['vol_type'] or "—"
                
                # Расчет использования пространства
                total = vol_row['total_space']
                used = vol_row['used_space']
                usage_pct = "0%"
                if total and total > 0 and used is not None:
                    usage_pct = f"{round((used / total) * 100, 1)}%"

                report_lines = [
                    "═" * 78,
                    f"  Gluster Volume-Inspector — Диагностический отчёт",
                    f"  Время: {now_naive.strftime('%d.%m.%Y %H:%M:%S')}",
                    "═" * 78,
                    "",
                    "ОСНОВНАЯ ИНФОРМАЦИЯ О ТОМЕ",
                    "─" * 78,
                    f"  Имя:            {_safe_text(vol_name)}",
                    f"  UUID:           {vid_search}",
                    f"  Кластер:        {_safe_text(cluster_name)}",
                    f"  Тип:            {_safe_text(vol_type)}",
                    f"  Статус:         {_safe_text(status)}",
                    f"  Использование:  {usage_pct} ({_safe_text(used)} / {_safe_text(total)} байт)",
                    "",
                ]

                # 2. Кирпичи (Bricks) через VIEW
                cur.execute("""
                    SELECT 
                        b.brick_dir,
                        b.vds_name,
                        b.interface_address,
                        b.status AS brick_status,
                        b.is_arbiter,
                        bd.used_space AS brick_used,
                        bd.total_space AS brick_total
                    FROM gluster_volume_bricks_view b
                    LEFT JOIN gluster_volume_brick_details bd ON b.id::text = bd.brick_id::text
                    WHERE b.volume_id::text = %s
                    ORDER BY b.brick_order
                """, (vid_search,))
                
                bricks = cur.fetchall()
                
                report_lines.append("КИРПИЧИ (BRICKS)")
                report_lines.append("─" * 78)
                
                if not bricks:
                    report_lines.append("    Кирпичи не обнаружены.")
                else:
                    for i, brick in enumerate(bricks, 1):
                        arbiter_marker = " [Arbiter]" if brick['is_arbiter'] else ""
                        brick_usage = ""
                        if brick['brick_total'] and brick['brick_total'] > 0 and brick['brick_used'] is not None:
                            pct = round((brick['brick_used'] / brick['brick_total']) * 100, 1)
                            brick_usage = f" | Заполнен: {pct}%"
                            
                        report_lines.append(f"    {i}. {_safe_text(brick['vds_name'])}: {_safe_text(brick['brick_dir'])}{arbiter_marker}")
                        report_lines.append(f"       Адрес: {_safe_text(brick['interface_address'])} | Статус: {_safe_text(brick['brick_status'])}{brick_usage}")
                        report_lines.append("")

                # 3. Опции тома
                cur.execute("""
                    SELECT option_key, option_val
                    FROM gluster_volume_options
                    WHERE volume_id::text = %s
                    ORDER BY option_key
                """, (vid_search,))
                
                options = cur.fetchall()
                
                report_lines.append("\nОПЦИИ ТОМА")
                report_lines.append("─" * 78)
                
                if not options:
                    report_lines.append("    Пользовательские опции не заданы.")
                else:
                    for opt in options:
                        report_lines.append(f"    • {_safe_text(opt['option_key'])} = {_safe_text(opt['option_val'])}")

                # 4. Geo-replication сессии
                cur.execute("""
                    SELECT 
                        ggs.slave_host_name,
                        ggs.slave_volume_name,
                        ggs.status AS geo_status,
                        ggs.user_name,
                        ggsd.checkpoint_status,
                        ggsd.data_pending,
                        ggsd.last_synced_at
                    FROM gluster_georep_session ggs
                    LEFT JOIN gluster_georep_session_details ggsd ON ggs.session_id = ggsd.session_id
                    WHERE ggs.master_volume_id::text = %s
                    ORDER BY ggs.slave_host_name
                """, (vid_search,))
                
                georep = cur.fetchall()
                
                report_lines.append("\nGEO-REPLICATION")
                report_lines.append("─" * 78)
                
                if not georep:
                    report_lines.append("    Сессии гео-репликации отсутствуют.")
                else:
                    for geo in georep:
                        pending = f"Pending: {geo['data_pending']}" if geo['data_pending'] else "No pending data"
                        synced = _safe_text(geo['last_synced_at'])
                        report_lines.append(f"    → {_safe_text(geo['slave_host_name'])}/{_safe_text(geo['slave_volume_name'])}")
                        report_lines.append(f"      Статус: {_safe_text(geo['geo_status'])} | Checkpoint: {_safe_text(geo['checkpoint_status'])}")
                        report_lines.append(f"      {pending} | Last Sync: {synced}")
                        report_lines.append("")

                # 5. Снапшоты
                cur.execute("""
                    SELECT snapshot_name, description, status, _create_date
                    FROM gluster_volume_snapshots
                    WHERE volume_id::text = %s
                    ORDER BY _create_date DESC
                """, (vid_search,))
                
                snapshots = cur.fetchall()
                
                report_lines.append("\nСНАПШОТЫ ТОМА")
                report_lines.append("─" * 78)
                
                if not snapshots:
                    report_lines.append("    Снапшоты отсутствуют.")
                else:
                    for snap in snapshots:
                        created = _safe_text(snap['_create_date'])
                        desc = _safe_text(snap['description']) or "—"
                        report_lines.append(f"    • {_safe_text(snap['snapshot_name'])} [{_safe_text(snap['status'])}]")
                        report_lines.append(f"      Создан: {created} | Описание: {desc}")
                        report_lines.append("")

                report_lines.append("\n" + "═" * 78)
                
                nav_data = {
                    "volume_id": vid_search,
                    "volume_name": vol_name,
                    "cluster_name": cluster_name,
                }

                return {
                    "report_text": "\n".join(report_lines),
                    "nav_data": nav_data
                }

    except Exception as e:
        return {"error": f"Ошибка инспектора: {e}", "report_text": "", "nav_data": {}}