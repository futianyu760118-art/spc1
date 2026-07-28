/* ============================================================================
 * 销售订单物料齐套分析 SQL  (金蝶 K3 — 经链接服务器 k3sv 查询)
 *
 * 用途：给定一张销售合同(订单)，对其下每个产品展开 BOM 子件，
 *       分别按「外购 / 委外 / 自制」核对库存与在途/在制量，得出齐套状态。
 *
 * 使用：把 @ContractNo 改成要查的销售合同单号即可。
 *       (合同单号见 t_RPContract.FContractNo，如 HJ202607-0002-0143)
 *
 * 依赖表：
 *   t_RPContract / t_rpContractEntry  销售合同主/明细
 *   t_ICItem                          物料主表 (FErpClsID: 1外购 2自制 3委外 5虚拟)
 *   ICBOM                             BOM 主表 (FUseStatus=1072 使用中, FStatus=1 已审核)
 *   ICBOMChild      / ICCustBOMChild   BOM 子件 (标准BOM子项 / 客户BOM子项, 二者结构相同)
 *   ICInventory                       即时库存
 *   POOrder / POOrderEntry             采购订单 (外购在途)
 *   ICSubContract / ICSubContractEntry 委外订单 (委外在制)
 *   ICMO                              生产任务单 (自制在制)
 * ============================================================================ */

DECLARE @ContractNo VARCHAR(64) = 'HJ202607-0002-0143';   -- ← 改成你的合同单号

;WITH
/* ---- 1. 销售合同的产品行 ---- */
SO AS (
    SELECT a.FContractNo, b.FEntryID, b.FProductID AS FItemID,
           c.FNumber  AS 产品代码,
           c.FName    AS 产品名称,
           b.FQuantity AS 订单数量,
           b.FDeliveryDate AS 交期
    FROM   k3sv.AIS20161019115614.dbo.t_RPContract        a
    JOIN   k3sv.AIS20161019115614.dbo.t_rpContractEntry    b ON a.FContractID = b.FContractID
    JOIN   k3sv.AIS20161019115614.dbo.t_ICItem             c ON b.FProductID  = c.FItemID
    JOIN   k3sv.AIS20161019115614.dbo.t_Department         d ON a.FDepartment = d.FItemID
    WHERE  a.FContractNo = @ContractNo
      AND  a.FChangeMark = 0                  -- 排除已变更/取消合同
      AND  a.FText NOT LIKE '%取消%'
      AND  d.FName <> '研发中心'              -- 排除研发合同
      AND  b.FQuantity > 0
),

/* ---- 2. 每个成品取「最新且有子件」的标准/客户 BOM ---- */
StdBOM AS (
    SELECT FInterID, FItemID
    FROM (
        SELECT b.FInterID, b.FItemID,
               ROW_NUMBER() OVER (PARTITION BY b.FItemID ORDER BY b.FCheckDate DESC) AS rn
        FROM   k3sv.AIS20161019115614.dbo.ICBOM b
        WHERE  b.FUseStatus = 1072          -- 使用中
          AND  b.FStatus    = 1             -- 已审核
          AND  EXISTS (                     -- 必须有子件(标准BOM子项 或 客户BOM子项)
                SELECT 1 FROM k3sv.AIS20161019115614.dbo.ICBOMChild    x WHERE x.FInterID = b.FInterID
                UNION ALL
                SELECT 1 FROM k3sv.AIS20161019115614.dbo.ICCustBOMChild x WHERE x.FInterID = b.FInterID)
    ) t
    WHERE rn = 1
),

/* ---- 3. BOM 子件 (标准 + 客户) 合并 ---- */
BOMChild AS (
    SELECT FInterID, FEntryID, FItemID, FQty FROM k3sv.AIS20161019115614.dbo.ICBOMChild
    UNION ALL
    SELECT FInterID, FEntryID, FItemID, FQty FROM k3sv.AIS20161019115614.dbo.ICCustBOMChild
),

/* ---- 4. 展开：成品 × 子件 × 单位用量 ---- */
BOMExp AS (
    SELECT so.FContractNo, so.产品代码, so.产品名称, so.订单数量, so.交期,
           ch.FItemID    AS 子物料ID,
           itm.FNumber   AS 子物料代码,
           itm.FName     AS 子物料名称,
           ch.FQty       AS 单位用量,
           itm.FErpClsID AS 物料属性
    FROM   SO      so
    JOIN   StdBOM  sb ON so.FItemID  = sb.FItemID
    JOIN   BOMChild ch ON sb.FInterID = ch.FInterID
    JOIN   k3sv.AIS20161019115614.dbo.t_ICItem itm ON ch.FItemID = itm.FItemID
),

/* ---- 5. 各类供应来源(按物料聚合) ---- */
Inv  AS (                                  -- 即时库存
    SELECT FItemID, SUM(FQty) AS 库存量
    FROM   k3sv.AIS20161019115614.dbo.ICInventory
    GROUP BY FItemID
),
PORem AS (                                 -- 外购: 采购订单未入库量(在途)
    SELECT pe.FItemID, SUM(pe.FQty - ISNULL(pe.FStockQty,0)) AS 采购在途量
    FROM   k3sv.AIS20161019115614.dbo.POOrder      po
    JOIN   k3sv.AIS20161019115614.dbo.POOrderEntry pe ON po.FInterID = pe.FInterID
    WHERE  po.FCancellation = 0 AND pe.FQty > ISNULL(pe.FStockQty,0)
    GROUP BY pe.FItemID
),
WWRem AS (                                 -- 委外: 委外订单未入库量(在制)
    SELECT se.FItemID, SUM(se.FQty - ISNULL(se.FStockQty,0)) AS 委外在制量
    FROM   k3sv.AIS20161019115614.dbo.ICSubContract      sc
    JOIN   k3sv.AIS20161019115614.dbo.ICSubContractEntry se ON sc.FInterID = se.FInterID
    WHERE  sc.FCancellation = 0 AND se.FQty > ISNULL(se.FStockQty,0)
    GROUP BY se.FItemID
),
MORem AS (                                 -- 自制: 生产任务单未入库量(在制)
    SELECT FItemID, SUM(FQty - ISNULL(FStockQty,0)) AS 生产在制量
    FROM   k3sv.AIS20161019115614.dbo.ICMO
    WHERE  FCancellation = 0 AND FQty > ISNULL(FStockQty,0)
    GROUP BY FItemID
)

/* ============================================================================
 *  结果一：物料齐套明细 (每个子物料一行)
 * ============================================================================ */
SELECT
    be.产品代码,
    be.产品名称,
    be.订单数量,
    CONVERT(CHAR(10), be.交期, 120)                                   AS 交期,
    be.子物料代码,
    be.子物料名称,
    CASE be.物料属性 WHEN 1 THEN '外购' WHEN 2 THEN '自制' WHEN 3 THEN '委外'
         WHEN 5 THEN '虚拟件' WHEN 7 THEN '配置类'
         ELSE CAST(be.物料属性 AS VARCHAR) END                         AS 供应方式,
    be.单位用量,
    CAST(be.订单数量 * be.单位用量 AS DECIMAL(18,2))                   AS 需求量,
    CAST(ISNULL(inv.库存量,0)      AS DECIMAL(18,2))                   AS 库存量,
    CAST(ISNULL(po.采购在途量,0)   AS DECIMAL(18,2))                   AS 采购在途量,
    CAST(ISNULL(ww.委外在制量,0)   AS DECIMAL(18,2))                   AS 委外在制量,
    CAST(ISNULL(mo.生产在制量,0)   AS DECIMAL(18,2))                   AS 生产在制量,
    CAST(ISNULL(inv.库存量,0)+ISNULL(po.采购在途量,0)
        +ISNULL(ww.委外在制量,0)+ISNULL(mo.生产在制量,0) AS DECIMAL(18,2)) AS 可用总量,
    CAST(be.订单数量 * be.单位用量
       - (ISNULL(inv.库存量,0)+ISNULL(po.采购在途量,0)
         +ISNULL(ww.委外在制量,0)+ISNULL(mo.生产在制量,0)) AS DECIMAL(18,2)) AS 缺口,
    CASE WHEN be.订单数量 * be.单位用量
          <= ISNULL(inv.库存量,0)+ISNULL(po.采购在途量,0)
            +ISNULL(ww.委外在制量,0)+ISNULL(mo.生产在制量,0)
         THEN '齐套' ELSE '欠料' END                                  AS 齐套状态
FROM BOMExp be
LEFT JOIN Inv  inv ON be.子物料ID = inv.FItemID
LEFT JOIN PORem po ON be.子物料ID = po.FItemID
LEFT JOIN WWRem ww ON be.子物料ID = ww.FItemID
LEFT JOIN MORem mo ON be.子物料ID = mo.FItemID
ORDER BY be.产品代码,
         CASE be.物料属性 WHEN 1 THEN 1 WHEN 3 THEN 2 WHEN 2 THEN 3 ELSE 9 END,
         be.子物料代码;
GO

/* ============================================================================
 *  结果二：按产品汇总齐套率 (每个产品一行)
 *  (注意: GO 会重置变量作用域, 故在此重新声明 @ContractNo)
 * ============================================================================ */
DECLARE @ContractNo2 VARCHAR(64) = 'HJ202607-0002-0143';   -- ← 与上面保持一致
;WITH
SO AS (
    SELECT a.FContractNo, b.FProductID AS FItemID, c.FNumber AS 产品代码, c.FName AS 产品名称,
           b.FQuantity AS 订单数量, b.FDeliveryDate AS 交期
    FROM   k3sv.AIS20161019115614.dbo.t_RPContract a
    JOIN   k3sv.AIS20161019115614.dbo.t_rpContractEntry b ON a.FContractID = b.FContractID
    JOIN   k3sv.AIS20161019115614.dbo.t_ICItem c ON b.FProductID = c.FItemID
    JOIN   k3sv.AIS20161019115614.dbo.t_Department d ON a.FDepartment = d.FItemID
    WHERE  a.FContractNo = @ContractNo2 AND a.FChangeMark = 0
      AND  a.FText NOT LIKE '%取消%' AND d.FName <> '研发中心' AND b.FQuantity > 0
),
StdBOM AS (
    SELECT FInterID, FItemID FROM (
        SELECT b.FInterID, b.FItemID,
               ROW_NUMBER() OVER (PARTITION BY b.FItemID ORDER BY b.FCheckDate DESC) rn
        FROM k3sv.AIS20161019115614.dbo.ICBOM b
        WHERE b.FUseStatus=1072 AND b.FStatus=1
          AND EXISTS(SELECT 1 FROM k3sv.AIS20161019115614.dbo.ICBOMChild    x WHERE x.FInterID=b.FInterID
             UNION ALL SELECT 1 FROM k3sv.AIS20161019115614.dbo.ICCustBOMChild x WHERE x.FInterID=b.FInterID)
    ) t WHERE rn=1
),
BOMChild AS (
    SELECT FInterID,FEntryID,FItemID,FQty FROM k3sv.AIS20161019115614.dbo.ICBOMChild
    UNION ALL
    SELECT FInterID,FEntryID,FItemID,FQty FROM k3sv.AIS20161019115614.dbo.ICCustBOMChild
),
BOMExp AS (
    SELECT so.产品代码, so.产品名称, so.订单数量, so.交期, ch.FItemID AS 子物料ID, ch.FQty AS 单位用量
    FROM SO so
    JOIN StdBOM sb ON so.FItemID=sb.FItemID
    JOIN BOMChild ch ON sb.FInterID=ch.FInterID
    JOIN k3sv.AIS20161019115614.dbo.t_ICItem itm ON ch.FItemID=itm.FItemID
),
Inv  AS (SELECT FItemID, SUM(FQty) 库存量 FROM k3sv.AIS20161019115614.dbo.ICInventory GROUP BY FItemID),
PORem AS (SELECT pe.FItemID, SUM(pe.FQty-ISNULL(pe.FStockQty,0)) 采购在途量 FROM k3sv.AIS20161019115614.dbo.POOrder po JOIN k3sv.AIS20161019115614.dbo.POOrderEntry pe ON po.FInterID=pe.FInterID WHERE po.FCancellation=0 AND pe.FQty>ISNULL(pe.FStockQty,0) GROUP BY pe.FItemID),
WWRem AS (SELECT se.FItemID, SUM(se.FQty-ISNULL(se.FStockQty,0)) 委外在制量 FROM k3sv.AIS20161019115614.dbo.ICSubContract sc JOIN k3sv.AIS20161019115614.dbo.ICSubContractEntry se ON sc.FInterID=se.FInterID WHERE sc.FCancellation=0 AND se.FQty>ISNULL(se.FStockQty,0) GROUP BY se.FItemID),
MORem AS (SELECT FItemID, SUM(FQty-ISNULL(FStockQty,0)) 生产在制量 FROM k3sv.AIS20161019115614.dbo.ICMO WHERE FCancellation=0 AND FQty>ISNULL(FStockQty,0) GROUP BY FItemID),
Det AS (
    SELECT be.产品代码, be.产品名称, be.订单数量, be.交期,
           CASE WHEN be.订单数量*be.单位用量
                <= ISNULL(inv.库存量,0)+ISNULL(po.采购在途量,0)+ISNULL(ww.委外在制量,0)+ISNULL(mo.生产在制量,0)
                THEN 1 ELSE 0 END AS 齐套标记
    FROM BOMExp be
    LEFT JOIN Inv  inv ON be.子物料ID=inv.FItemID
    LEFT JOIN PORem po ON be.子物料ID=po.FItemID
    LEFT JOIN WWRem ww ON be.子物料ID=ww.FItemID
    LEFT JOIN MORem mo ON be.子物料ID=mo.FItemID
)
SELECT 产品代码, 产品名称, 订单数量, CONVERT(CHAR(10),交期,120) AS 交期,
       COUNT(*)            AS 子件总数,
       SUM(齐套标记)       AS 已齐套数,
       COUNT(*)-SUM(齐套标记) AS 欠料数,
       CAST(1.0*SUM(齐套标记)/COUNT(*)*100 AS DECIMAL(5,1)) AS 齐套率,
       CASE WHEN SUM(齐套标记)=COUNT(*) THEN '齐套' ELSE '欠料' END AS 整体状态
FROM Det
GROUP BY 产品代码, 产品名称, 订单数量, 交期
ORDER BY 齐套率, 产品代码;
GO
