import streamlit as st
import pandas as pd
import io

# ================= 1. 配置与映射 (保持 V2.2 确认版) =================
COLUMN_MAPS = {
    'WP (WesternPost)': {
        'SKU': 'SKU', 'Warehouse': '仓库/Warehouse', 
        'Qty': '数量/Quantity', 'Fee': '金额/Amount', 
        'Age': '库龄/Library of Age', 'Vol': '体积(m³)'
    },
    'LG (乐仓)': {
        'SKU': '乐仓货品编码', 'Warehouse': '仓库', 
        'Qty': '数量', 'Fee': '计算金额', 
        'Age': '库龄', 'Vol': '总体积'
    },
    'AI (AI仓)': {
        'SKU': 'SKU', 'Warehouse': '仓库', 
        'Qty': '库存', 'Fee': '费用', 
        'Age': '在库天数', 'Vol': '立方数'
    },
    'WL (WWL)': {
        'SKU': '商品SKU', 'Warehouse': '实际发货仓库', 
        'Qty': '库存总数_QTY', 'Fee': '计费总价', 
        'Age': '库存库龄_CD', 'Vol': '计费总体积_立方米'
    }
}

AGE_BINS = [0, 30, 60, 90, 120, 180, 360, 9999]
AGE_LABELS = ['0-30天', '31-60天', '61-90天', '91-120天', '120-180天', '180-360天', '360天+']

# ================= 2. 数据处理函数 (V2.3 智能读取升级) =================
def load_and_clean_data(file, provider):
    try:
        # 🌟 核心修改：不再依赖文件名后缀，采用“双重保险”读取法
        df = None
        
        # 尝试方法 A: 当作 Excel 读取
        try:
            df = pd.read_excel(file)
        except:
            # 如果失败，重置文件指针，尝试方法 B: 当作 CSV 读取
            file.seek(0)
            try:
                # 兼容常见的编码问题 (utf-8 或 gbk)
                df = pd.read_csv(file, encoding='utf-8')
            except:
                file.seek(0)
                df = pd.read_csv(file, encoding='gbk')
        
        if df is None:
            st.error(f"❌ {provider} 文件读取失败，请检查文件是否损坏。")
            return pd.DataFrame()

        # 数据清洗逻辑 (保持不变)
        mapping = COLUMN_MAPS[provider]
        
        # 去除表头可能存在的空格 (防止 ' 仓库' 这种隐形错误)
        df.columns = df.columns.str.strip()
        
        valid_map = {k: v for k, v in mapping.items() if v in df.columns}
        rename_dict = {v: k for k, v in valid_map.items()}
        df = df.rename(columns=rename_dict)
        
        required_cols = ['SKU', 'Warehouse', 'Qty', 'Fee', 'Age', 'Vol']
        for col in required_cols:
            if col not in df.columns: df[col] = 0 
                
        for col in ['Qty', 'Fee', 'Age', 'Vol']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        df['Age_Range'] = pd.cut(df['Age'], bins=AGE_BINS, labels=AGE_LABELS, right=False)
        df['Age_Range'] = df['Age_Range'].cat.add_categories(['未知']).fillna('360天+')
        df['Provider'] = provider
        
        return df
        
    except Exception as e:
        st.error(f"解析 {provider} 文件发生未知错误: {str(e)}")
        return pd.DataFrame()

# ================= 3. 界面逻辑 =================
st.set_page_config(page_title="海外仓库存分析 V2.3", page_icon="🏭", layout="wide")
st.title("🏭 海外仓分仓库存分析 (V2.3)")
st.caption("更新点：智能识别文件格式 | 不限制文件名 | 兼容 CSV/Excel")

# --- 侧边栏：数据上传 ---
with st.sidebar:
    st.header("1. 数据上传")
    st.info("💡 提示：无需修改文件名，直接上传原始导出的表格即可。")
    dfs = []
    for provider in COLUMN_MAPS.keys():
        f = st.file_uploader(f"上传 {provider} 数据", type=['xlsx', 'xls', 'csv'], key=provider)
        if f:
            df = load_and_clean_data(f, provider)
            if not df.empty:
                dfs.append(df)

if not dfs:
    st.info("👈 请在左侧上传库存数据文件")
else:
    full_df = pd.concat(dfs, ignore_index=True)
    st.divider()
    
    c1, c2 = st.columns(2)
    with c1:
        selected_provider = st.selectbox("① 选择部门 / 服务商", full_df['Provider'].unique())
    
    provider_df = full_df[full_df['Provider'] == selected_provider]
    warehouse_list = sorted(provider_df['Warehouse'].astype(str).unique().tolist())
    warehouse_list.insert(0, "全部 (All Warehouses)")
    
    with c2:
        selected_warehouse = st.selectbox("② 选择仓库", warehouse_list)
    
    if selected_warehouse == "全部 (All Warehouses)":
        target_df = provider_df
        display_wh_name = "全仓库汇总"
    else:
        target_df = provider_df[provider_df['Warehouse'] == selected_warehouse]
        display_wh_name = selected_warehouse
    
    total_qty = target_df['Qty'].sum()
    total_vol = target_df['Vol'].sum()
    total_fee = target_df['Fee'].sum()
    
    summary = target_df.groupby('Age_Range').agg({'Qty': 'sum', 'Vol': 'sum', 'Fee': 'sum'})
    summary['库存占比'] = (summary['Qty'] / total_qty * 100).fillna(0) if total_qty else 0
    summary['体积占比'] = (summary['Vol'] / total_vol * 100).fillna(0) if total_vol else 0
    summary['费用占比'] = (summary['Fee'] / total_fee * 100).fillna(0) if total_fee else 0
    
    display_summary = summary.copy()
    display_summary['Qty'] = display_summary['Qty'].map('{:,.0f}'.format)
    display_summary['Vol'] = display_summary['Vol'].map('{:,.2f} m³'.format)
    display_summary['Fee'] = display_summary['Fee'].map('${:,.2f}'.format)
    display_summary['库存占比'] = display_summary['库存占比'].map('{:.1f}%'.format)
    display_summary['体积占比'] = display_summary['体积占比'].map('{:.1f}%'.format)
    display_summary['费用占比'] = display_summary['费用占比'].map('{:.1f}%'.format)
    
    st.markdown(f"### 📊 {selected_provider} - {display_wh_name}")
    k1, k2, k3 = st.columns(3)
    k1.metric("总库存 (PCS)", f"{total_qty:,.0f}")
    k2.metric("总体积 (CBM)", f"{total_vol:,.2f}")
    k3.metric("总费用 (USD)", f"${total_fee:,.2f}")
    
    st.markdown("#### A. 库龄结构总览")
    st.dataframe(display_summary[['Qty', '库存占比', 'Vol', '体积占比', 'Fee', '费用占比']], use_container_width=True)
    
    st.divider()
    st.markdown("#### B. 异常库存深钻 (Top 20 SKU)")
    target_age_range = st.radio("选择要深挖的库龄段：", AGE_LABELS, horizontal=True, index=len(AGE_LABELS)-1)
    
    drill_df = target_df[target_df['Age_Range'] == target_age_range]
    if drill_df.empty:
        st.warning(f"在 {display_wh_name} 中，{target_age_range} 库龄段没有库存。")
    else:
        top_20 = drill_df.sort_values(by='Fee', ascending=False).head(20)
        top_20_show = top_20[['SKU', 'Warehouse', 'Qty', 'Vol', 'Fee', 'Age']].copy()
        top_20_show.columns = ['SKU', '所在仓库', '库存数量', '体积(m³)', '仓租费用($)', '具体库龄(天)']
        st.write(f"🔍 **{target_age_range}** - 费用最高的 Top 20 SKU：")
        st.dataframe(top_20_show.style.background_gradient(subset=['仓租费用($)'], cmap='Reds'), use_container_width=True)