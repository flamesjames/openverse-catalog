from common.loader import paths, s3, sql
from common.loader.paths import _extract_media_type
from common.loader.reporting import RecordMetrics


def copy_to_s3(output_dir, bucket, identifier, aws_conn_id):
    tsv_file_name = paths.get_staged_file(output_dir, identifier)
    media_type = _extract_media_type(tsv_file_name)
    s3.copy_file_to_s3_staging(
        identifier, tsv_file_name, bucket, aws_conn_id, media_prefix=media_type
    )


def load_s3_data(
    bucket,
    aws_conn_id,
    postgres_conn_id,
    identifier,
    ti,
):
    media_type = ti.xcom_pull(task_ids="stage_oldest_tsv_file", key="media_type")
    tsv_version = ti.xcom_pull(task_ids="stage_oldest_tsv_file", key="tsv_version")

    if media_type is None:
        media_type = "image"
    tsv_key = s3.get_staged_s3_object(
        identifier, bucket, aws_conn_id, media_prefix=media_type
    )
    sql.load_s3_data_to_intermediate_table(
        postgres_conn_id, bucket, tsv_key, identifier, media_type
    )
    sql.upsert_records_to_db_table(
        postgres_conn_id, identifier, media_type=media_type, tsv_version=tsv_version
    )


def upsert_data(
    postgres_conn_id: str,
    media_type: str,
    tsv_version: str,
    identifier: str,
    loaded_count: int,
    duplicates_count: tuple[int, int],
) -> RecordMetrics:
    """
    Upserts data into the catalog DB from the loading table, and calculates
    final record metrics.
    """
    missing_columns, foreign_id_dup = duplicates_count
    upserted = sql.upsert_records_to_db_table(
        postgres_conn_id, identifier, media_type=media_type, tsv_version=tsv_version
    )

    url_dup = loaded_count - missing_columns - foreign_id_dup - upserted
    return RecordMetrics(upserted, missing_columns, foreign_id_dup, url_dup)
