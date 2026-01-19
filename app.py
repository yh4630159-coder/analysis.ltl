import streamlit as st
import pandas as pd
import io

# ================= 1. 配置与映射 =================
COLUMN_MAPS = {
    'WP': { # WesternPost
        'SKU': 'SKU', 'Warehouse': '仓库/Warehouse', 
        'Qty': '数量/Quantity', 'Fee': '金额/Amount', 
        'Age': '库龄/Library of Age', 'Vol': '体积(m³)',
        'Full_Name': 'WesternPost'
    },
    'LG': { # 乐仓
        'SKU': '乐仓货品编码', 'Warehouse': '仓库', 
        'Qty': '数量', 'Fee': '计算金额', 
        'Age': '库龄', 'Vol': '总体积',
        'Full_Name': 'Lecangs'
    },
    'AI': { # AI仓
        'SKU': 'SKU', 'Warehouse': '仓库', 
        'Qty': '库存', 'Fee': '费用', 
        'Age': '在库天数', 'Vol': '立方数',
        'Full_Name': 'AI'
    },
    'WL': { # 万邑通
        'SKU': '商品SKU', 'Warehouse': '实际发货仓库', 
        'Qty': '库存总数_QTY', 'Fee': '计费总价', 
        'Age': '库存库龄_CD', 'Vol': '计费总体积_立方米',
        'Full_Name': 'WWL'
    }
}

AGE_BINS = [0, 30, 60, 90, 120, 180, 360, 99999]
AGE_LABELS = ['0-30天', '31-60天', '61-90天', '91-120天', '120-180天', '180-360天', '360天+']

# ================= 2. 核心处理逻辑 (V2.7内核 + V3.0扩展) =================

def parse_filename(filename):
    """
    解析文件名：部门_服务商_日期.xlsx
    """
    name_body = filename.rsplit('.', 1)[0]
    parts = name_body.split('_')
    
    if len(parts) >= 3:
        dept = parts[0]
        # 尝试匹配服务商代码 (忽略大小写)
        raw_code = parts[1].upper()
        provider_code = None
        for key in COLUMN_MAPS.keys():
            if key in raw_code:
                provider_code = key
                break
        
        date_str = parts[2]
        return dept, provider_code, date_str
    return None, None, None

def load_data_v3_1(file):
    # 1. 解析文件名
    dept, provider_code, date_str = parse_filename(file.name)
    
    # 模糊匹配逻辑 (兼容旧文件)
    if not dept:
        dept = "默认部门"
        for code in COLUMN_MAPS.keys():
            if code in file.name.upper():
                provider_code = code
                break
        date_str = "最新"

    if not provider_code:
        st.toast(f"⚠️ 跳过无法识别的文件: {file.name}", icon="⏭️")
        return pd.DataFrame()

    # 2. 读取文件 (V2.7 强力读取逻辑)
    df = None
    try: df = pd.read_excel(file, engine='openpyxl', header=None); 
    except: pass
    if df is None:
        try: file.seek(0); df = pd.read_csv(file, encoding='utf-8', header=None)
        except: pass
    if df is None:
        try: file.seek(0); df = pd.read_csv(file, encoding='gb18030', header=None)
        except: pass
            
    if df is None:
        return pd.DataFrame()

    try:
        mapping = COLUMN_MAPS[provider_code]
        
        # 3. 智能定位表头 (V2.7 修复 WL 偏移问题)
        header_idx = 0
        expected_cols = set(mapping.values())
        expected_cols.discard(mapping.get('Full_Name')) # 去除元数据key
        
        for i in range(min(20, len(df))):
            row_values = df.iloc[i].astype(str).str.strip().tolist()
            row_values = [x.replace('\ufeff', '') for x in row_values]
            match_count = sum(1 for x in row_values if x in expected_cols)
            if match_count >= 2:
                header_idx = i
                break
        
        new_columns = df.iloc[header_idx].astype(str).str.strip().str.replace('\ufeff', '')
        df = df.iloc[header_idx+1:].copy()
        df.columns = new_columns

        # 4. 清洗与转换
        valid_map = {k: v for k, v in mapping.items() if v in df.columns}
        rename_dict = {v: k for k, v in valid_map.items()}
        df = df.rename(columns=rename_dict)
        
        required_cols = ['SKU', 'Warehouse', 'Qty', 'Fee', 'Age', 'Vol']
        for col in required_cols:
            if col not in df.columns: df[col] = 0 
                
        for col in ['Qty', 'Fee', 'Age', 'Vol']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        # 5. 库龄分段 (V2.7 强制纯文本防错)
        cut_series = pd.cut(df['Age'], bins=AGE_BINS, labels=AGE_LABELS, right=False)
        df['Age_Range'] = cut_series.astype(str)
        df.loc[df['Age_Range'] == 'nan', 'Age_Range'] = '360天+'
        df['Age_Range'] = df['Age_Range'].str.strip()

        # 6. 注入元数据 (V3.0 特性)
        df['Dept'] = dept
        df['Provider'] = mapping['Full_Name']
        df['Date'] = date_str
        
        return df
        
    except Exception as e:
        return pd.DataFrame()

# ================= 3. 界面逻辑 =================
st.set_page_config(page_title="海外仓库存 BI V3.1", page_icon="📈", layout="wide")
st.title("📈 海外仓多部门趋势分析看板 (V3.1)")

with st.expander("ℹ️ 文件命名规范 (推荐)", expanded=False):
    st.markdown("""
    为了实现趋势对比，建议将文件重命名为：**`部门_服务商_日期.xlsx`**
    * 示例：`业务一部_AI_2024-01.xlsx`
    * 服务商代码支持：AI, WL, LG, WP
    """)

# --- 侧边栏：批量上传 ---
with st.sidebar:
    st.header("📂 数据中心")
    uploaded_files = st.file_uploader(
        "批量上传所有文件 (支持多选)", 
        type=['xlsx', 'xls', 'csv'], 
        accept_multiple_files=True
    )
    
    dfs = []
    if uploaded_files:
        bar = st.progress(0)
        for i, file in enumerate(uploaded_files):
            df = load_data_v3_1(file)
            if not df.empty:
                dfs.append(df)
            bar.progress((i + 1) / len(uploaded_files))
        st.success(f"已加载 {len(dfs)} 个文件")

if not dfs:
    st.info("👈 请在左侧上传文件")
else:
    full_df = pd.concat(dfs, ignore_index=True)
    
    # 选项卡
    tab1, tab2 = st.tabs(["📊 月度详情深钻 (V2.7功能)", "📈 历史趋势对比 (V3.0功能)"])
    
    # ================= TAB 1: 详情分析 (集成 V2.7 修复版) =================
    with tab1:
        c1, c2, c3 = st.columns(3)
        with c1:
            sel_dept = st.selectbox("选择部门", full_df['Dept'].unique(), key='t1_dept')
        with c2:
            dept_df = full_df[full_df['Dept'] == sel_dept]
            # 日期倒序排列
            sel_date = st.selectbox("选择月份", sorted(dept_df['Date'].unique(), reverse=True), key='t1_date')
        with c3:
            date_df = dept_df[dept_df['Date'] == sel_date]
            sel_prov = st.selectbox("选择服务商", date_df['Provider'].unique(), key='t1_prov')
            
        target_df = date_df[date_df['Provider'] == sel_prov]
        
        wh_list = sorted(target_df['Warehouse'].astype(str).unique().tolist())
        wh_list.insert(0, "全部汇总 (All Warehouses)")
        sel_wh = st.selectbox("选择仓库", wh_list, key='t1_wh')
        
        if sel_wh != "全部汇总 (All Warehouses)":
            final_df = target_df[target_df['Warehouse'] == sel_wh]
            wh_name = sel_wh
        else:
            final_df = target_df
            wh_name = "全仓汇总"
            
        # 统计数据
        total_fee = final_df['Fee'].sum()
        total_vol = final_df['Vol'].sum()
        total_qty = final_df['Qty'].sum()
        
        k1, k2, k3 = st.columns(3)
        k1.metric("总库存", f"{total_qty:,.0f}")
        k2.metric("总体积", f"{total_vol:,.2f} m³")
        k3.metric("总费用", f"${total_fee:,.2f}")
        
        # 库龄表
        summary = final_df.groupby('Age_Range').agg({'Fee': 'sum', 'Qty': 'sum', 'Vol': 'sum'}).reset_index()
        order_map = {label: i for i, label in enumerate(AGE_LABELS)}
        summary['sort'] = summary['Age_Range'].map(order_map).fillna(999)
        summary = summary.sort_values('sort').drop('sort', axis=1)
        
        summary['费用占比'] = (summary['Fee'] / total_fee * 100).fillna(0) if total_fee else 0
        summary['库存占比'] = (summary['Qty'] / total_qty * 100).fillna(0) if total_qty else 0
        
        # 展示主表
        display = summary.copy()
        display['Fee'] = display['Fee'].map('${:,.2f}'.format)
        display['Vol'] = display['Vol'].map('{:,.2f}'.format)
        display['Qty'] = display['Qty'].map('{:,.0f}'.format)
        display['费用占比'] = display['费用占比'].map('{:.1f}%'.format)
        display['库存占比'] = display['库存占比'].map('{:.1f}%'.format)
        
        st.dataframe(display[['Age_Range', 'Qty', '库存占比', 'Vol', 'Fee', '费用占比']], hide_index=True, use_container_width=True)
        
        # Deep Dive (V2.7 修复版逻辑)
        st.divider()
        st.markdown("#### 🔍 异常库存深钻 (Top 20)")
        
        # 🌟 V2.7 Fix: 动态生成且去重的选项
        present_ages = final_df['Age_Range'].unique().tolist()
        sorted_ages = [label for label in AGE_LABELS if label in present_ages]
        
        if not sorted_ages:
            st.warning("暂无数据。")
        else:
            rng = st.radio("选择库龄段", sorted_ages, horizontal=True, index=len(sorted_ages)-1, key='t1_radio')
            drill = final_df[final_df['Age_Range'] == rng]
            
            if drill.empty:
                st.info("无数据。")
            else:
                top20 = drill.sort_values(by='Fee', ascending=False).head(20)
                top20_show = top20[['SKU','Warehouse','Qty','Vol','Fee','Age']].copy()
                top20_show.columns = ['SKU','所在仓库','库存','体积','费用','库龄']
                
                # 安全渲染
                try:
                    styled = top20_show.style.format({'费用': '${:.2f}', '体积': '{:.2f}'})\
                        .background_gradient(subset=['费用'], cmap='Reds')
                    st.dataframe(styled, use_container_width=True)
                except:
                    st.dataframe(top20_show, use_container_width=True)

    # ================= TAB 2: 趋势分析 (V3.0) =================
    with tab2:
        st.markdown("#### 📈 历史趋势对比")
        
        cc1, cc2 = st.columns(2)
        with cc1:
            t_dept = st.selectbox("分析部门", full_df['Dept'].unique(), key='t2_dept')
        with cc2:
            t_data = full_df[full_df['Dept'] == t_dept]
            t_prov = st.selectbox("分析服务商", t_data['Provider'].unique(), key='t2_prov')
            
        t_final = t_data[t_data['Provider'] == t_prov]
        
        t_wh_list = sorted(t_final['Warehouse'].astype(str).unique().tolist())
        t_wh_list.insert(0, "全部汇总")
        t_wh = st.selectbox("分析仓库", t_wh_list, key='t2_wh')
        
        if t_wh != "全部汇总":
            trend_source = t_final[t_final['Warehouse'] == t_wh]
        else:
            trend_source = t_final
            
        if len(trend_source['Date'].unique()) < 2:
            st.warning("⚠️ 数据不足：当前筛选条件下只有一个月份的数据，无法生成趋势图。请上传更多月份的文件。")
        else:
            # 数据聚合
            trend_agg = trend_source.groupby('Date').agg({
                'Fee': 'sum', 'Vol': 'sum', 'Qty': 'sum'
            }).reset_index().sort_values('Date')
            
            # 1. 组合图
            st.markdown("##### 💰 费用(Bar) 与 体积(Line) 趋势")
            chart_data = trend_agg.set_index('Date')[['Fee', 'Vol']]
            st.bar_chart(chart_data['Fee'], color='#FF4B4B')
            st.line_chart(chart_data['Vol'], color='#0000FF')
            
            # 2. 呆滞趋势
            st.markdown("##### ⚠️ 360天+ 呆滞费用趋势")
            dead_stock = trend_source[trend_source['Age_Range'] == '360天+']
            if dead_stock.empty:
                st.success("表现优秀！该时间段内无 360天+ 呆滞库存。")
            else:
                dead_trend = dead_stock.groupby('Date')['Fee'].sum().reset_index().sort_values('Date')
                st.area_chart(dead_trend.set_index('Date'), color='#808080')
            
            # 3. 数据表
            st.markdown("##### 📋 详细数据表")
            pivot = trend_agg.set_index('Date').T
            st.dataframe(pivot.style.format("{:,.2f}"), use_container_width=True)