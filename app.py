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

AGE_BINS = [0, 30, 60, 90, 120, 180, 360, 99999]
AGE_LABELS = ['0-30天', '31-60天', '61-90天', '91-120天', '120-180天', '180-360天', '360天+']

# ================= 2. 智能数据处理函数 =================
def find_header_row(df, mapping, max_scan=10):
    """
    智能查找表头：扫描前N行，看哪一行包含最多的期望列名
    """
    best_score = 0
    best_header_row = 0
    expected_cols = set(mapping.values())
    
    # 扫描 DataFrame 的前几行
    for i in range(min(len(df), max_scan)):
        # 获取这一行的数据作为潜在表头
        row_values = df.iloc[i].astype(str).str.strip().tolist()
        # 计算匹配度 (有多少列名对上了)
        score = sum(1 for col in row_values if col in expected_cols)
        
        if score > best_score:
            best_score = score
            best_header_row = i
            
    # 如果匹配度太低（比如小于2个），可能不需要跳过，保持默认
    if best_score < 2:
        return 0
    
    # 返回表头所在的行号（Excel里的行号，pandas读取时需要+1，因为iloc是从0开始的数据行）
    return best_header_row + 1

def load_and_clean_data(file, provider):
    df = None
    
    # --- 阶段一：读取文件 (格式兼容) ---
    try:
        df = pd.read_excel(file, engine='openpyxl', header=None) # 先不指定header，全部读进来
    except:
        pass

    if df is None:
        try:
            file.seek(0)
            df = pd.read_csv(file, encoding='utf-8', header=None)
        except:
            pass

    if df is None:
        try:
            file.seek(0)
            df = pd.read_csv(file, encoding='gb18030', header=None)
        except:
            pass
            
    if df is None:
        st.error(f"❌ 解析失败：{provider} 文件无法读取。")
        return pd.DataFrame()

    try:
        mapping = COLUMN_MAPS[provider]
        
        # --- 阶段二：智能定位表头 (Header Hunter) ---
        # 很多文件(如WL)表头不在第一行，我们需要找到它
        header_idx = 0
        expected_cols = set(mapping.values())
        
        # 扫描前20行寻找包含关键列名的行
        for i in range(min(20, len(df))):
            row_values = df.iloc[i].astype(str).str.strip().tolist()
            # 简单去BOM
            row_values = [x.replace('\ufeff', '') for x in row_values]
            
            # 如果这一行包含至少2个我们要找的列名，就认定它是表头
            match_count = sum(1 for x in row_values if x in expected_cols)
            if match_count >= 2:
                header_idx = i
                break
        
        # 重建 DataFrame，使用找到的表头行
        # 将第 i 行设为列名，取 i+1 行及之后的数据
        new_columns = df.iloc[header_idx].astype(str).str.strip().str.replace('\ufeff', '')
        df = df.iloc[header_idx+1:].copy()
        df.columns = new_columns

        # --- 阶段三：标准清洗 ---
        # 映射重命名
        valid_map = {k: v for k, v in mapping.items() if v in df.columns}
        rename_dict = {v: k for k, v in valid_map.items()}
        df = df.rename(columns=rename_dict)
        
        # 补全缺失列
        required_cols = ['SKU', 'Warehouse', 'Qty', 'Fee', 'Age', 'Vol']
        for col in required_cols:
            if col not in df.columns: df[col] = 0 
                
        # 转换数值类型
        for col in ['Qty', 'Fee', 'Age', 'Vol']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        # 库龄分段 (强制纯文本)
        cut_series = pd.cut(df['Age'], bins=AGE_BINS, labels=AGE_LABELS, right=False)
        df['Age_Range'] = cut_series.astype(str)
        df.loc[df['Age_Range'] == 'nan', 'Age_Range'] = '360天+'
        df['Age_Range'] = df['Age_Range'].str.strip()

        df['Provider'] = provider
        return df
        
    except Exception as e:
        st.error(f"⚠️ {provider} 数据清洗出错: {str(e)}")
        return pd.DataFrame()

# ================= 3. 界面逻辑 =================
st.set_page_config(page_title="海外仓库存分析 V2.7", page_icon="🏭", layout="wide")
st.title("🏭 海外仓分仓库存分析 (V2.7)")
st.caption("✅ 更新：智能表头定位(WL修复) | 渲染安全模式(防闪退)")

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
    
    # 统计展示
    total_qty = target_df['Qty'].sum()
    total_vol = target_df['Vol'].sum()
    total_fee = target_df['Fee'].sum()
    
    # 聚合
    summary = target_df.groupby('Age_Range').agg({'Qty': 'sum', 'Vol': 'sum', 'Fee': 'sum'}).reset_index()
    
    # 排序
    order_map = {label: i for i, label in enumerate(AGE_LABELS + ['360天+'])}
    summary['sort_key'] = summary['Age_Range'].map(order_map).fillna(999)
    summary = summary.sort_values('sort_key').drop('sort_key', axis=1)

    # 占比计算
    summary['库存占比'] = (summary['Qty'] / total_qty * 100).fillna(0) if total_qty else 0
    summary['体积占比'] = (summary['Vol'] / total_vol * 100).fillna(0) if total_vol else 0
    summary['费用占比'] = (summary['Fee'] / total_fee * 100).fillna(0) if total_fee else 0
    
    # 汇总表展示
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
    
    # 动态选项
    available_ages = [label for label in (AGE_LABELS + ['360天+']) if label in target_df['Age_Range'].unique()]
    
    if not available_ages:
        st.warning("暂无数据。")
    else:
        age_rng = st.radio("选择库龄段：", available_ages, horizontal=True, index=len(available_ages)-1)
        drill = target_df[target_df['Age_Range'] == age_rng]
        
        if drill.empty:
            st.info("无数据。")
        else:
            try:
                top20 = drill.sort_values(by='Fee', ascending=False).head(20)
                
                # 准备展示数据
                top20_show = top20[['SKU', 'Warehouse', 'Qty', 'Vol', 'Fee', 'Age']].copy()
                top20_show.columns = ['SKU', '所在仓库', '库存数量', '体积(m³)', '仓租费用($)', '具体库龄(天)']
                
                st.write(f"🔍 **{age_rng}** - 费用最高的 Top 20 SKU：")
                
                # 🌟 安全渲染模式 (Safe Styling)
                try:
                    # 尝试带颜色的漂亮表格
                    styled_df = top20_show.style.format({
                        '仓租费用($)': '${:.2f}',
                        '体积(m³)': '{:.2f}',
                        '具体库龄(天)': '{:.0f}'
                    }).background_gradient(subset=['仓租费用($)'], cmap='Reds')
                    
                    st.dataframe(styled_df, use_container_width=True)
                    
                except Exception as style_err:
                    # 如果上色失败（比如数据全为0导致渐变计算错误），直接显示黑白表格
                    # st.warning(f"渲染样式时遇到小问题，已自动切换到兼容模式。") 
                    st.dataframe(top20_show, use_container_width=True)
                    
            except Exception as e:
                st.error(f"生成列表时出错: {e}")