import streamlit as st
import pandas as pd
import io

# ================= 1. 配置与映射 (保持不变) =================
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

# ================= 2. 数据处理函数 (V2.4 无限制版) =================
def load_and_clean_data(file, provider):
    # 🌟 核心修改：完全忽略 file.name 后缀，直接读取内容
    df = None
    
    # --- 第一关：尝试作为 Excel 读取 ---
    try:
        # engine='openpyxl' 是最通用的 Excel 引擎
        df = pd.read_excel(file, engine='openpyxl')
    except:
        pass # 失败不要紧，继续试下一关

    # --- 第二关：尝试作为 CSV 读取 (UTF-8) ---
    if df is None:
        try:
            file.seek(0) # 必须把指针重置到文件开头
            df = pd.read_csv(file, encoding='utf-8')
        except:
            pass

    # --- 第三关：尝试作为 CSV 读取 (GBK/GB18030 - 解决中文乱码) ---
    if df is None:
        try:
            file.seek(0)
            df = pd.read_csv(file, encoding='gb18030')
        except:
            pass
            
    # --- 最终判定 ---
    if df is None:
        st.error(f"❌ 解析失败：{provider} 的文件既不是 Excel 也不是 CSV，或者已损坏。")
        return pd.DataFrame()

    # --- 数据清洗逻辑 ---
    try:
        mapping = COLUMN_MAPS[provider]
        
        # 清理表头空格 (防止 'SKU ' 这种隐形坑)
        df.columns = df.columns.astype(str).str.strip()
        
        # 映射重命名
        valid_map = {k: v for k, v in mapping.items() if v in df.columns}
        rename_dict = {v: k for k, v in valid_map.items()}
        df = df.rename(columns=rename_dict)
        
        # 补全列
        required_cols = ['SKU', 'Warehouse', 'Qty', 'Fee', 'Age', 'Vol']
        for col in required_cols:
            if col not in df.columns: df[col] = 0 
                
        # 转换数字
        for col in ['Qty', 'Fee', 'Age', 'Vol']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        # 生成库龄
        df['Age_Range'] = pd.cut(df['Age'], bins=AGE_BINS, labels=AGE_LABELS, right=False)
        df['Age_Range'] = df['Age_Range'].cat.add_categories(['未知']).fillna('360天+')
        df['Provider'] = provider
        
        return df
        
    except Exception as e:
        st.error(f"⚠️ {provider} 数据处理出错: {str(e)}")
        return pd.DataFrame()

# ================= 3. 界面逻辑 =================
st.set_page_config(page_title="海外仓库存分析 V2.4", page_icon="🏭", layout="wide")
st.title("🏭 海外仓分仓库存分析 (V2.4)")
st.caption("✅ 终极版：文件名无限制 | 自动识别文件格式")

# --- 侧边栏 ---
with st.sidebar:
    st.header("1. 数据上传")
    st.info("💡 只要是表格文件都能传，不需要改名。")
    dfs = []
    for provider in COLUMN_MAPS.keys():
        # accept_multiple_files=False, 但去掉了 type 限制，任何文件都能选
        f = st.file_uploader(f"上传 {provider} 数据", key=provider)
        if f:
            df = load_and_clean_data(f, provider)
            if not df.empty:
                dfs.append(df)

if not dfs:
    st.info("👈 请在左侧上传文件")
else:
    full_df = pd.concat(dfs, ignore_index=True)
    st.divider()
    
    c1, c2 = st.columns(2)
    with c1:
        selected_provider = st.selectbox("① 选择部门", full_df['Provider'].unique())
    
    provider_df = full_df[full_df['Provider'] == selected_provider]
    wh_list = sorted(provider_df['Warehouse'].astype(str).unique().tolist())
    wh_list.insert(0, "全部 (All Warehouses)")
    
    with c2:
        selected_wh = st.selectbox("② 选择仓库", wh_list)
    
    if selected_wh == "全部 (All Warehouses)":
        target_df = provider_df
        display_name = "全仓库汇总"
    else:
        target_df = provider_df[provider_df['Warehouse'] == selected_wh]
        display_name = selected_wh
    
    total_qty = target_df['Qty'].sum()
    total_vol = target_df['Vol'].sum()
    total_fee = target_df['Fee'].sum()
    
    summary = target_df.groupby('Age_Range').agg({'Qty': 'sum', 'Vol': 'sum', 'Fee': 'sum'})
    summary['库存占比'] = (summary['Qty'] / total_qty * 100).fillna(0) if total_qty else 0
    summary['体积占比'] = (summary['Vol'] / total_vol * 100).fillna(0) if total_vol else 0
    summary['费用占比'] = (summary['Fee'] / total_fee * 100).fillna(0) if total_fee else 0
    
    # 展示逻辑
    display = summary.copy()
    display['Qty'] = display['Qty'].map('{:,.0f}'.format)
    display['Vol'] = display['Vol'].map('{:,.2f} m³'.format)
    display['Fee'] = display['Fee'].map('${:,.2f}'.format)
    display['库存占比'] = display['库存占比'].map('{:.1f}%'.format)
    display['体积占比'] = display['体积占比'].map('{:.1f}%'.format)
    display['费用占比'] = display['费用占比'].map('{:.1f}%'.format)
    
    st.markdown(f"### 📊 {selected_provider} - {display_name}")
    k1, k2, k3 = st.columns(3)
    k1.metric("总库存", f"{total_qty:,.0f}")
    k2.metric("总体积", f"{total_vol:,.2f}")
    k3.metric("总费用", f"${total_fee:,.2f}")
    
    st.dataframe(display[['Qty', '库存占比', 'Vol', '体积占比', 'Fee', '费用占比']], use_container_width=True)
    
    st.divider()
    st.markdown("#### B. 异常库存深钻 (Top 20 SKU)")
    age_rng = st.radio("选择库龄段：", AGE_LABELS, horizontal=True, index=len(AGE_LABELS)-1)
    
    drill = target_df[target_df['Age_Range'] == age_rng]
    if drill.empty:
        st.warning(f"没有数据。")
    else:
        top20 = drill.sort_values(by='Fee', ascending=False).head(20)
        top20_show = top20[['SKU', 'Warehouse', 'Qty', 'Vol', 'Fee', 'Age']].copy()
        top20_show.columns = ['SKU', '所在仓库', '库存数量', '体积(m³)', '仓租费用($)', '具体库龄(天)']
        st.dataframe(top20_show.style.background_gradient(subset=['仓租费用($)'], cmap='Reds'), use_container_width=True)