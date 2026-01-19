import streamlit as st
import pandas as pd
import io

# ================= 1. 配置与映射 =================
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

AGE_BINS = [0, 30, 60, 90, 120, 180, 360, 99999] # 扩大上限
AGE_LABELS = ['0-30天', '31-60天', '61-90天', '91-120天', '120-180天', '180-360天', '360天+']

# ================= 2. 数据处理函数 =================
def load_and_clean_data(file, provider):
    # 1. 尝试读取 (兼容各种格式)
    df = None
    try:
        df = pd.read_excel(file, engine='openpyxl')
    except:
        pass

    if df is None:
        try:
            file.seek(0)
            df = pd.read_csv(file, encoding='utf-8')
        except:
            pass

    if df is None:
        try:
            file.seek(0)
            df = pd.read_csv(file, encoding='gb18030')
        except:
            pass
            
    if df is None:
        st.error(f"❌ 解析失败：{provider} 文件无法读取。")
        return pd.DataFrame()

    try:
        mapping = COLUMN_MAPS[provider]
        df.columns = df.columns.astype(str).str.strip()
        
        valid_map = {k: v for k, v in mapping.items() if v in df.columns}
        rename_dict = {v: k for k, v in valid_map.items()}
        df = df.rename(columns=rename_dict)
        
        required_cols = ['SKU', 'Warehouse', 'Qty', 'Fee', 'Age', 'Vol']
        for col in required_cols:
            if col not in df.columns: df[col] = 0 
                
        for col in ['Qty', 'Fee', 'Age', 'Vol']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        # 🌟 V2.6 核心修改：库龄分段逻辑重写
        # 1. 先用 cut 分段
        cut_series = pd.cut(df['Age'], bins=AGE_BINS, labels=AGE_LABELS, right=False)
        
        # 2. 🌟 强制转换为纯字符串 (String)，彻底消除 Category 类型隐患
        df['Age_Range'] = cut_series.astype(str)
        
        # 3. 处理 NaN (转字符串后变成了 'nan')
        df.loc[df['Age_Range'] == 'nan', 'Age_Range'] = '360天+'
        
        # 4. 去除可能存在的空格
        df['Age_Range'] = df['Age_Range'].str.strip()

        df['Provider'] = provider
        return df
        
    except Exception as e:
        st.error(f"⚠️ {provider} 数据处理出错: {str(e)}")
        return pd.DataFrame()

# ================= 3. 界面逻辑 =================
st.set_page_config(page_title="海外仓库存分析 V2.6", page_icon="🏭", layout="wide")
st.title("🏭 海外仓分仓库存分析 (V2.6)")
st.caption("✅ 修复点：强制统一数据类型，解决有数据却报错的问题")

with st.sidebar:
    st.header("1. 数据上传")
    dfs = []
    for provider in COLUMN_MAPS.keys():
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
    
    # --- 统计展示区 ---
    total_qty = target_df['Qty'].sum()
    total_vol = target_df['Vol'].sum()
    total_fee = target_df['Fee'].sum()
    
    # 聚合计算
    summary = target_df.groupby('Age_Range').agg({'Qty': 'sum', 'Vol': 'sum', 'Fee': 'sum'}).reset_index()
    
    # 🌟 排序逻辑优化：手动指定顺序，防止字母顺序干扰
    order_map = {label: i for i, label in enumerate(AGE_LABELS + ['360天+'])}
    summary['sort_key'] = summary['Age_Range'].map(order_map).fillna(999)
    summary = summary.sort_values('sort_key').drop('sort_key', axis=1)

    summary['库存占比'] = (summary['Qty'] / total_qty * 100).fillna(0) if total_qty else 0
    summary['体积占比'] = (summary['Vol'] / total_vol * 100).fillna(0) if total_vol else 0
    summary['费用占比'] = (summary['Fee'] / total_fee * 100).fillna(0) if total_fee else 0
    
    # 格式化
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
    
    st.dataframe(display[['Age_Range', 'Qty', '库存占比', 'Vol', '体积占比', 'Fee', '费用占比']], hide_index=True, use_container_width=True)
    
    st.divider()
    st.markdown("#### B. 异常库存深钻 (Top 20 SKU)")
    
    # 选择器
    # 🌟 动态生成选项：只显示当前数据中存在的库龄段，避免选到空的
    available_ages = [label for label in (AGE_LABELS + ['360天+']) if label in target_df['Age_Range'].unique()]
    
    if not available_ages:
        st.warning("当前仓库没有库存数据。")
    else:
        # 默认选最大的那个库龄段
        default_index = len(available_ages) - 1
        age_rng = st.radio("选择库龄段：", available_ages, horizontal=True, index=default_index)
        
        # 筛选数据
        drill = target_df[target_df['Age_Range'] == age_rng]
        
        # 🌟 调试信息：如果还是报错，点开这个看原因
        with st.expander("🛠️ 如果报错，请点开查看调试信息"):
            st.write(f"当前选中的库龄段: '{age_rng}' (类型: {type(age_rng)})")
            st.write(f"筛选出的行数: {len(drill)}")
            if not drill.empty:
                st.write("前5行预览:", drill.head())
            else:
                st.write("⚠️ 警告：筛选结果为空，可能是字符串匹配失败。")
                st.write("数据中实际存在的库龄段:", target_df['Age_Range'].unique())

        if drill.empty:
            st.info(f"✨ 恭喜！在 **{display_name}** 中，**{age_rng}** 库龄段没有发现库存。")
        else:
            try:
                top20 = drill.sort_values(by='Fee', ascending=False).head(20)
                
                top20_show = top20[['SKU', 'Warehouse', 'Qty', 'Vol', 'Fee', 'Age']].copy()
                top20_show.columns = ['SKU', '所在仓库', '库存数量', '体积(m³)', '仓租费用($)', '具体库龄(天)']
                
                st.write(f"🔍 **{age_rng}** - 费用最高的 Top 20 SKU：")
                st.dataframe(
                    top20_show.style.format({
                        '仓租费用($)': '${:.2f}',
                        '体积(m³)': '{:.2f}',
                        '具体库龄(天)': '{:.0f}'
                    }).background_gradient(subset=['仓租费用($)'], cmap='Reds'),
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"生成 Top 20 列表时出错: {e}")