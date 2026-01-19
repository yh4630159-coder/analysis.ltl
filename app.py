import streamlit as st
import pandas as pd
import io

# ================= 1. 配置与映射 (V2.2 最终校准) =================
COLUMN_MAPS = {
    'WP (WesternPost)': {
        'SKU': 'SKU', 
        'Warehouse': '仓库/Warehouse', 
        'Qty': '数量/Quantity', 
        'Fee': '金额/Amount', 
        'Age': '库龄/Library of Age', 
        'Vol': '体积(m³)'  # 保持不变
    },
    'LG (乐仓)': {
        'SKU': '乐仓货品编码', 
        'Warehouse': '仓库', 
        'Qty': '数量', 
        'Fee': '计算金额', 
        'Age': '库龄', 
        'Vol': '总体积'  # 保持不变
    },
    'AI (AI仓)': {
        'SKU': 'SKU', 
        'Warehouse': '仓库', 
        'Qty': '库存', 
        'Fee': '费用', 
        'Age': '在库天数', 
        'Vol': '立方数'  # ✅ 已确认为“立方数”
    },
    'WL (WWL)': {
        'SKU': '商品SKU', 
        'Warehouse': '实际发货仓库', # ✅ 已修正为“实际发货仓库”
        'Qty': '库存总数_QTY', 
        'Fee': '计费总价', 
        'Age': '库存库龄_CD', 
        'Vol': '计费总体积_立方米' # 保持之前确认的
    }
}

# 库龄分段规则
AGE_BINS = [0, 30, 60, 90, 120, 180, 360, 9999]
AGE_LABELS = ['0-30天', '31-60天', '61-90天', '91-120天', '120-180天', '180-360天', '360天+']

# ================= 2. 数据处理函数 =================
def load_and_clean_data(file, provider):
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
            
        mapping = COLUMN_MAPS[provider]
        
        # 1. 重命名列 (只重命名存在的列)
        valid_map = {k: v for k, v in mapping.items() if v in df.columns}
        rename_dict = {v: k for k, v in valid_map.items()}
        df = df.rename(columns=rename_dict)
        
        # 2. 补全缺失列
        required_cols = ['SKU', 'Warehouse', 'Qty', 'Fee', 'Age', 'Vol']
        for col in required_cols:
            if col not in df.columns:
                df[col] = 0 
                
        # 3. 强制类型转换
        for col in ['Qty', 'Fee', 'Age', 'Vol']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        # 4. 生成库龄段
        df['Age_Range'] = pd.cut(df['Age'], bins=AGE_BINS, labels=AGE_LABELS, right=False)
        df['Age_Range'] = df['Age_Range'].cat.add_categories(['未知']).fillna('360天+')
        
        df['Provider'] = provider
        return df
        
    except Exception as e:
        st.error(f"解析 {provider} 文件失败: {str(e)}")
        return pd.DataFrame()

# ================= 3. 界面逻辑 =================
st.set_page_config(page_title="海外仓库存分析 V2.2", page_icon="🏭", layout="wide")
st.title("🏭 海外仓分仓库存分析 (V2.2)")
st.caption("更新点：修正WL仓库列名 | 确认AI体积列名 | 完整分仓汇总")

# --- 侧边栏：数据上传 ---
with st.sidebar:
    st.header("1. 数据上传")
    dfs = []
    for provider in COLUMN_MAPS.keys():
        f = st.file_uploader(f"上传 {provider} 数据", type=['xlsx', 'csv'], key=provider)
        if f:
            df = load_and_clean_data(f, provider)
            if not df.empty:
                dfs.append(df)

if not dfs:
    st.info("👈 请在左侧上传库存数据文件")
else:
    # 合并所有数据
    full_df = pd.concat(dfs, ignore_index=True)
    
    # --- 筛选区域 ---
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        # 选择部门
        selected_provider = st.selectbox("① 选择部门 / 服务商", full_df['Provider'].unique())
    
    # 获取该部门下的仓库列表
    provider_df = full_df[full_df['Provider'] == selected_provider]
    
    # 🌟 核心修改：添加“全部”选项
    warehouse_list = sorted(provider_df['Warehouse'].astype(str).unique().tolist())
    warehouse_list.insert(0, "全部 (All Warehouses)")
    
    with c2:
        selected_warehouse = st.selectbox("② 选择仓库", warehouse_list)
    
    # --- 数据过滤逻辑 ---
    if selected_warehouse == "全部 (All Warehouses)":
        target_df = provider_df # 不过滤，取全部
        display_wh_name = "全仓库汇总"
    else:
        target_df = provider_df[provider_df['Warehouse'] == selected_warehouse]
        display_wh_name = selected_warehouse
    
    # --- 计算统计 ---
    total_qty = target_df['Qty'].sum()
    total_vol = target_df['Vol'].sum()
    total_fee = target_df['Fee'].sum()
    
    # 1. 汇总透视表
    summary = target_df.groupby('Age_Range').agg({
        'Qty': 'sum',
        'Vol': 'sum',
        'Fee': 'sum'
    })
    
    # 计算占比
    summary['库存占比'] = (summary['Qty'] / total_qty * 100).fillna(0) if total_qty else 0
    summary['体积占比'] = (summary['Vol'] / total_vol * 100).fillna(0) if total_vol else 0
    summary['费用占比'] = (summary['Fee'] / total_fee * 100).fillna(0) if total_fee else 0
    
    # 格式化
    display_summary = summary.copy()
    display_summary['Qty'] = display_summary['Qty'].map('{:,.0f}'.format)
    display_summary['Vol'] = display_summary['Vol'].map('{:,.2f} m³'.format)
    display_summary['Fee'] = display_summary['Fee'].map('${:,.2f}'.format)
    display_summary['库存占比'] = display_summary['库存占比'].map('{:.1f}%'.format)
    display_summary['体积占比'] = display_summary['体积占比'].map('{:.1f}%'.format)
    display_summary['费用占比'] = display_summary['费用占比'].map('{:.1f}%'.format)
    
    display_summary = display_summary[['Qty', '库存占比', 'Vol', '体积占比', 'Fee', '费用占比']]
    
    # --- 页面展示 ---
    st.markdown(f"### 📊 {selected_provider} - {display_wh_name}")
    
    k1, k2, k3 = st.columns(3)
    k1.metric("总库存 (PCS)", f"{total_qty:,.0f}")
    k2.metric("总体积 (CBM)", f"{total_vol:,.2f}")
    k3.metric("总费用 (USD)", f"${total_fee:,.2f}")
    
    st.markdown("#### A. 库龄结构总览")
    st.dataframe(display_summary, use_container_width=True)
    
    st.divider()
    st.markdown("#### B. 异常库存深钻 (Top 20 SKU)")
    
    target_age_range = st.radio(
        "选择要深挖的库龄段：", 
        AGE_LABELS, 
        horizontal=True,
        index=len(AGE_LABELS)-1 
    )
    
    drill_df = target_df[target_df['Age_Range'] == target_age_range]
    
    if drill_df.empty:
        st.warning(f"在 {display_wh_name} 中，{target_age_range} 库龄段没有库存。")
    else:
        top_20 = drill_df.sort_values(by='Fee', ascending=False).head(20)
        
        # 显示 Top 20 详情
        cols_to_show = ['SKU', 'Warehouse', 'Qty', 'Vol', 'Fee', 'Age']
        col_names = ['SKU', '所在仓库', '库存数量', '体积(m³)', '仓租费用($)', '具体库龄(天)']
        
        top_20_show = top_20[cols_to_show].copy()
        top_20_show.columns = col_names
        
        st.write(f"🔍 **{target_age_range}** - 费用最高的 Top 20 SKU：")
        st.dataframe(
            top_20_show.style.background_gradient(subset=['仓租费用($)'], cmap='Reds'),
            use_container_width=True
        )