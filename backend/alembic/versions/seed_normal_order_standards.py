"""seed normal order standards

Revision ID: seed_normal_order_standards
Revises: add_employee_org_relation_oa_user_id, add_md_display_fields, add_supplier_account_to_purchase_order, add_supplier_name_to_sys_user
Create Date: 2026-06-09 13:30:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "seed_normal_order_standards"
down_revision: Union[str, Sequence[str], None] = (
    "add_employee_org_relation_oa_user_id",
    "add_md_display_fields",
    "add_supplier_account_to_purchase_order",
    "add_supplier_name_to_sys_user",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ORDER_STANDARD_CONTENT = """21、订单总交付标准周期为31天，供应链内部交付期为28天。其中物料采购周期为20天，组、包装车间周期为5天，前道车间、光电车间、品质部检验包含在供应链内部交付期合理安排。这个是正常订单的标准，特殊的就可以手动调整。

24、物料齐套装配车间标准：组装7天齐套，包装包材3天齐套。同时执行包材提前送大货样进行检验，成品支架提前3天送大货样进行检验，合格后待通知送货。"""


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO node_standard (
            node_code,
            node_name,
            time_value,
            time_unit,
            applicable_scene,
            description,
            is_active,
            created_by
        )
        VALUES
            ('NORMAL_ORDER_TOTAL_DELIVERY', '正常订单总交付标准周期', 31, '天', '通用', '订单总交付标准周期为31天', true, 'admin'),
            ('SUPPLY_CHAIN_INTERNAL_DELIVERY', '供应链内部交付期', 28, '天', '通用', '供应链内部交付期为28天', true, 'admin'),
            ('MATERIAL_PROCUREMENT_CYCLE', '物料采购周期', 20, '天', '通用', '物料采购周期为20天', true, 'admin'),
            ('ASSEMBLY_PACKAGING_WORKSHOP_CYCLE', '组、包装车间周期', 5, '天', '通用', '组、包装车间周期为5天', true, 'admin'),
            ('ASSEMBLY_MATERIAL_KIT_READY', '组装齐套标准', 7, '天', '通用', '组装7天齐套', true, 'admin'),
            ('PACKAGING_MATERIAL_KIT_READY', '包装包材齐套标准', 3, '天', '通用', '包装包材3天齐套', true, 'admin'),
            ('FINISHED_BRACKET_SAMPLE_INSPECTION_ADVANCE', '成品支架大货样检验提前期', 3, '天', '通用', '成品支架提前3天送大货样进行检验', true, 'admin')
        ON CONFLICT (node_code) DO UPDATE
        SET node_name = EXCLUDED.node_name,
            time_value = EXCLUDED.time_value,
            time_unit = EXCLUDED.time_unit,
            applicable_scene = EXCLUDED.applicable_scene,
            description = EXCLUDED.description,
            is_active = EXCLUDED.is_active,
            created_by = COALESCE(node_standard.created_by, EXCLUDED.created_by),
            updated_at = now()
        """
    )

    op.execute(
        f"""
        WITH upserted_document AS (
            INSERT INTO business_document (
                doc_type,
                code,
                title,
                applicable_product,
                applicable_order,
                applicable_process,
                current_version,
                status,
                created_by
            )
            VALUES (
                'order_standard',
                'STD-NORMAL-ORDER-DELIVERY',
                '正常订单交付与物料齐套标准',
                NULL,
                '正常订单',
                NULL,
                'V1.0',
                'published',
                'admin'
            )
            ON CONFLICT (doc_type, code) DO UPDATE
            SET title = EXCLUDED.title,
                applicable_product = EXCLUDED.applicable_product,
                applicable_order = EXCLUDED.applicable_order,
                applicable_process = EXCLUDED.applicable_process,
                current_version = EXCLUDED.current_version,
                status = EXCLUDED.status,
                updated_at = now()
            RETURNING id
        )
        INSERT INTO business_document_version (
            document_id,
            version_no,
            content,
            attachments,
            status,
            effective_date,
            published_at,
            published_by,
            created_by
        )
        SELECT
            id,
            'V1.0',
            $content${ORDER_STANDARD_CONTENT}$content$,
            '[]'::jsonb,
            'published',
            DATE '2026-06-09',
            now(),
            'admin',
            'admin'
        FROM upserted_document
        ON CONFLICT (document_id, version_no) DO UPDATE
        SET content = EXCLUDED.content,
            attachments = EXCLUDED.attachments,
            status = EXCLUDED.status,
            effective_date = EXCLUDED.effective_date,
            published_at = COALESCE(business_document_version.published_at, EXCLUDED.published_at),
            published_by = EXCLUDED.published_by,
            updated_at = now()
        """
    )


def downgrade() -> None:
    # Keep seeded business standards intact on downgrade to avoid deleting
    # configuration that may have been edited after migration.
    pass
