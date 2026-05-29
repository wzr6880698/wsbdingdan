import streamlit as st
import pandas as pd
import re
from datetime import datetime
import numpy as np

# --------------------------
# 页面配置
# --------------------------
st.set_page_config(page_title="未匹配订单明细提取工具", layout="wide")
st.title("📊 未匹配订单明细提取 & 状态筛选 & 金额计算")
st.markdown("功能：从明细表中提取**未在报送表中出现**的订单明细 → 剔除无效状态 → 计算订单金额 → 导出结果")


# --------------------------
# 工具函数
# --------------------------
def find_order_column(df, default_text="订单号"):
    """自动寻找订单号列"""
    columns = [str(col).strip() for col in df.columns]
    keywords = ["订单号", "订单编号", "订单ID", "order no", "order id", "orderno", "orderid"]
    match_scores = []

    for col in columns:
        score = 0
        col_lower = col.lower()
        for kw in keywords:
            if kw in col_lower:
                score += 10
            if col_lower == kw:
                score += 20
        match_scores.append((col, score))

    match_scores.sort(key=lambda x: x[1], reverse=True)
    best_col = match_scores[0][0] if match_scores else columns[0]
    return best_col


def clean_order_no(value):
    """清洗订单号：去空格、转字符串"""
    if pd.isna(value):
        return ""
    return str(value).strip()


# --------------------------
# 1. 文件上传
# --------------------------
st.subheader("1️⃣ 上传文件")
col1, col2 = st.columns(2)

with col1:
    sum_file = st.file_uploader("上传【订单报送表】", type=["xlsx", "xls"])
with col2:
    detail_file = st.file_uploader("上传【订单明细表】", type=["xlsx", "xls"])

sum_df = None
detail_df = None

if sum_file:
    sum_df = pd.read_excel(sum_file)
    st.success(f"✅ 报送表已加载：{sum_df.shape[0]} 行")

if detail_file:
    detail_df = pd.read_excel(detail_file)
    st.success(f"✅ 明细表已加载：{detail_df.shape[0]} 行")

# --------------------------
# 2. 选择订单号列
# --------------------------
if sum_df is not None and detail_df is not None:
    st.subheader("2️⃣ 选择订单号匹配列")
    col1, col2 = st.columns(2)

    with col1:
        sum_order_col = st.selectbox(
            "报送表订单号列",
            options=sum_df.columns.tolist(),
            index=sum_df.columns.tolist().index(find_order_column(sum_df)) if find_order_column(
                sum_df) in sum_df.columns else 0
        )

    with col2:
        detail_order_col = st.selectbox(
            "明细表订单号列",
            options=detail_df.columns.tolist(),
            index=detail_df.columns.tolist().index(find_order_column(detail_df)) if find_order_column(
                detail_df) in detail_df.columns else 0
        )

    # --------------------------
    # 3. 执行反向匹配（核心：未匹配数据）
    # --------------------------
    st.subheader("3️⃣ 未匹配原始数据（未筛选）")

    # 清洗订单号
    sum_df["清洗后订单号"] = sum_df[sum_order_col].apply(clean_order_no)
    detail_df["清洗后订单号"] = detail_df[detail_order_col].apply(clean_order_no)

    # 汇总表订单号集合
    sum_order_set = set(sum_df["清洗后订单号"].unique())

    # 取明细表中【不在汇总表里】的数据
    unmatch_df = detail_df[~detail_df["清洗后订单号"].isin(sum_order_set)].copy()
    unmatch_df = unmatch_df.drop(columns=["清洗后订单号"])

    st.metric("📌 未匹配原始明细行数", f"{len(unmatch_df)} 行")
    st.dataframe(unmatch_df.head(30), use_container_width=True)

    # --------------------------
    # 4. 状态筛选：剔除指定状态（核心需求1）
    # --------------------------
    st.subheader("4️⃣ 状态筛选结果（剔除无效状态）")
    filter_df = unmatch_df.copy()

    # 状态列固定为 N 列（索引13，因为从0开始）
    status_col = filter_df.columns[13] if len(filter_df.columns) > 13 else None
    st.info(f"✅ 自动识别状态列：{status_col}（表格N列）")

    # 需要剔除的状态
    exclude_status = [
        "待买家付款",
        "待买家支付预付款",
        "待卖家接单",
        "订单关闭"
    ]

    if status_col is not None:
        # 剔除这些状态
        filter_df = filter_df[~filter_df[status_col].isin(exclude_status)]
        st.metric("📌 筛选后有效行数", f"{len(filter_df)} 行")
    else:
        st.warning("⚠️ 表格不足N列，请检查文件格式")

    st.dataframe(filter_df.head(30), use_container_width=True)

    # --------------------------
    # 5. 计算订单金额 = 数量 × 单价（核心需求2）
    # --------------------------
    st.subheader("5️⃣ 订单金额计算结果")
    final_df = filter_df.copy()

    # 匹配列名
    qty_col = None
    price_col = None
    for col in final_df.columns:
        col_lower = str(col).lower()
        if "quantity" in col_lower or "数量" in col_lower:
            qty_col = col
        if "unit price" in col_lower or "单价" in col_lower:
            price_col = col

    if qty_col and price_col:
        # 转数值，避免错误
        final_df[qty_col] = pd.to_numeric(final_df[qty_col], errors="coerce").fillna(0)
        final_df[price_col] = pd.to_numeric(final_df[price_col], errors="coerce").fillna(0)

        # 在【最后一列】新增 订单金额
        final_df["订单金额"] = final_df[qty_col] * final_df[price_col]
        st.success(f"✅ 订单金额计算完成：{qty_col} × {price_col}")
    else:
        st.warning("⚠️ 未找到 数量/单价 列，无法计算金额")

    st.dataframe(final_df.head(30), use_container_width=True)

    # --------------------------
    # 6. 汇总统计
    # --------------------------
    st.subheader("6️⃣ 最终数据统计")
    total_orders = final_df[detail_order_col].nunique()
    total_rows = len(final_df)
    total_amount = final_df["订单金额"].sum() if "订单金额" in final_df.columns else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("有效未匹配订单数", total_orders)
    col2.metric("明细总行数", total_rows)
    col3.metric("总订单金额", round(total_amount, 2))

    # --------------------------
    # 7. 导出文件（已修复：无报错 + 强制订单号为文本）
    # --------------------------
    st.subheader("7️⃣ 导出最终结果")
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"未匹配有效订单明细_{now}.xlsx"

    # ✅ 核心修复：强制订单号列转为纯文本（彻底解决科学计数法）
    final_df[detail_order_col] = final_df[detail_order_col].astype(str).str.strip()
    # 把 nan 换成空字符串
    final_df[detail_order_col] = final_df[detail_order_col].replace("nan", "")

    # ✅ 安全导出，无报错
    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        final_df.to_excel(writer, sheet_name="有效未匹配数据", index=False)

    # 提供下载
    with open(filename, "rb") as f:
        st.download_button(
            label="📥 下载最终结果表",
            data=f,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

else:
    st.info("请先上传 报送表 + 明细表")