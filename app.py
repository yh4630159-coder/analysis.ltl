import streamlit as st
import pandas as pd
import io
import re

# ================= 1. 配置与映射 (V2.7 基础) =================
COLUMN_MAPS = {
    'WP': { # WesternPost 简写匹配文件名
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

# ================= 2. 核心处理逻辑 =================

def parse_filename(filename):
    """
    解析文件名，提取：部门、服务商、日期
    期望格式：部门_服务商_YYYY-MM.xlsx (例如：业务一部_AI_2024-01.xlsx)
    """
    # 去掉后缀
    name_body = filename.rsplit('.', 1)[0]
    parts = name_body.split('_')
    
    if len(parts) >= 3:
        dept = parts[0]
        provider_code = parts[1].upper() # 转大写以匹配 key
        date_str = parts[2]
        return dept, provider_code, date_str
    return None, None, None

def find_header_row(df, mapping, max_scan=10):
    best_score = 0
    best_header_row = 0
    expected_cols = set(mapping.values())
    expected_cols.discard(mapping.get('Full_Name')) # 去掉非列名的key
    
    for i in range(min(len(df), max_scan)):
        row_values = df.iloc[i].astype(str).str.strip().tolist()
        score = sum(1 for col in row_values if col in expected_cols)
        if score > best_score:
            best_score = score
            best_header_row = i
    if best_score < 2: return 0
    return best_header_row + 1

def load_data_v3(file):
    # 1. 解析文件名
    dept, provider_code, date_str = parse_filename(file.name)
    
    # 如果文件名不符合规则，尝试模糊匹配 (为了兼容旧习惯，默认为未知部门)
    if not dept:
        dept = "默认部门"
        # 尝试从文件名猜服务商
        for code in COLUMN_MAPS.keys():
            if code in file.name.upper():
                provider_code = code
                break
        date_str = "最新" # 无法解析日期

    if provider_code not in COLUMN_MAPS:
        st.toast(f"⚠️ 跳过文件 {file.name}: 无法识别服务商(AI/WL/LG/WP)", icon="⏭️")
        return pd.DataFrame()

    # 2. 读取内容 (V2.7 的强力读取逻辑)
    df = None
    try: df = pd.read_excel(file, engine='openpyxl', header=None) 
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
        
        # 智能表头
        header_idx = 0
        expected_cols = set(mapping.values())
        expected_cols.discard(mapping.get('Full_Name'))
        
        for i in range(min(20, len(df))):
            row_values = df.iloc[i].astype(str).str.strip().tolist()
            row_values = [x.replace('\ufeff', '') for x in row_values]
            if sum(1 for x in row_values if x in expected_cols) >= 2:
                header_idx = i
                break
        
        new_columns = df.iloc[header_idx].astype(str).str.strip().str.replace('\ufeff', '')
        df = df.iloc[header_idx+1:].copy()
        df.columns = new_columns

        # 标准清洗
        valid_map = {k: v for k, v in mapping.items() if v in df.columns}
        rename_dict = {v: k for k, v in valid_map.items()}
        df = df.rename(columns=rename_dict)
        
        for col in ['Qty', 'Fee', 'Age', 'Vol']:
            if col not in df.columns: df[col] = 0
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        # 库龄处理
        cut_series = pd.cut(df['Age'], bins=AGE_BINS, labels=AGE_LABELS, right=False)
        df['Age_Range'] = cut_series.astype(str)
        df.loc[df['Age_Range'] == 'nan', 'Age_Range'] = '360天+'
        df['Age_Range'] = df['Age_Range'].str.strip()

        # 🌟 V3.0 新增维度
        df['Dept'] = dept
        df['Provider'] = mapping['Full_Name']
        df['Date'] = date_str
        
        return df
        
    except Exception as e:
        return pd.DataFrame()

# ================= 3. 界面逻辑 =================
st.set_page_config(page_title="海外仓库存 BI V3.0", page_icon="📈", layout="wide")
st.title("📈 海外仓多部门趋势分析看板 (V3.0)")

with st.expander("ℹ️ 使用指南 & 命名规范 (必读)", expanded=False):
    st.markdown("""
    **要想实现趋势对比，请务必按以下格式重命名文件：**
    
    `部门名称_服务商代码_日期.xlsx`
    
    * **部门名称**：例如 业务一部、业务二部、Amazon团队
    * **服务商代码**：必须包含 **AI, WL, LG, WP** 其中之一
    * **日期**：例如 2024-01, 2024-02
    
    **✅ 正确示例：** `业务一部_AI_2024-01.xlsx`
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
        progress_bar = st.progress(0)
        for i, file in enumerate(uploaded_files):
            df = load_data_v3(file)
            if not df.empty:
                dfs.append(df)
            progress_bar.progress((i + 1) / len(uploaded_files))
        st.success(f"成功读取 {len(dfs)} 个文件")

if not dfs:
    st.info("👈 请在左侧上传带有【部门_服务商_日期】命名的文件，即可开启趋势分析。")
else:
    full_df = pd.concat(dfs, ignore_index=True)
    
    # 选项卡切换
    tab1, tab2 = st.tabs(["📊 单月/单部门详情 (V2.7视图)", "📈 历史趋势对比 (V3.0视图)"])
    
    # ================= TAB 1: 详情分析 =================
    with tab1:
        c1, c2, c3 = st.columns(3)
        with c1:
            # 级联选择
            sel_dept = st.selectbox("选择部门", full_df['Dept'].unique(), key='t1_dept')
        with c2:
            # 根据部门筛选日期
            dept_df = full_df[full_df['Dept'] == sel_dept]
            sel_date = st.selectbox("选择月份", sorted(dept_df['Date'].unique(), reverse=True), key='t1_date')
        with c3:
            # 根据部门和日期筛选服务商
            date_df = dept_df[dept_df['Date'] == sel_date]
            sel_prov = st.selectbox("选择服务商", date_df['Provider'].unique(), key='t1_prov')
            
        # 最终筛选
        target_df = date_df[date_df['Provider'] == sel_prov]
        
        # 仓库选择
        wh_list = sorted(target_df['Warehouse'].astype(str).unique().tolist())
        wh_list.insert(0, "全部 (All Warehouses)")
        sel_wh = st.selectbox("选择仓库", wh_list, key='t1_wh')
        
        if sel_wh != "全部 (All Warehouses)":
            final_df = target_df[target_df['Warehouse'] == sel_wh]
            wh_name = sel_wh
        else:
            final_df = target_df
            wh_name = "全仓汇总"
            
        # --- 渲染 V2.7 的图表 ---
        # (此处复用之前的统计逻辑，精简展示)
        total_fee = final_df['Fee'].sum()
        total_vol = final_df['Vol'].sum()
        
        k1, k2 = st.columns(2)
        k1.metric("当月总费用", f"${total_fee:,.2f}")
        k2.metric("当月总体积", f"{total_vol:,.2f} m³")
        
        # 库龄表
        summary = final_df.groupby('Age_Range').agg({'Fee': 'sum', 'Qty': 'sum', 'Vol': 'sum'}).reset_index()
        order_map = {label: i for i, label in enumerate(AGE_LABELS + ['360天+'])}
        summary['sort'] = summary['Age_Range'].map(order_map).fillna(999)
        summary = summary.sort_values('sort').drop('sort', axis=1)
        
        summary['费用占比'] = (summary['Fee'] / total_fee * 100).fillna(0)
        
        st.dataframe(
            summary.style.format({'Fee': '${:.2f}', '费用占比': '{:.1f}%', 'Vol': '{:.2f}'})
            .background_gradient(subset=['Fee'], cmap='Blues'),
            use_container_width=True
        )
        
        # Deep Dive
        with st.expander("🔍 异常库存深钻 (Top 20)", expanded=True):
            avail_ages = [l for l in (AGE_LABELS + ['360天+']) if l in final_df['Age_Range'].unique()]
            if avail_ages:
                rng = st.radio("库龄段", avail_ages, horizontal=True, index=len(avail_ages)-1)
                drill = final_df[final_df['Age_Range'] == rng]
                top20 = drill.sort_values(by='Fee', ascending=False).head(20)
                st.dataframe(top20[['SKU','Warehouse','Qty','Fee','Age']], use_container_width=True)

    # ================= TAB 2: 趋势分析 (核心新功能) =================
    with tab2:
        st.markdown("#### 📈 部门库存/费用走势图")
        
        cc1, cc2 = st.columns(2)
        with cc1:
            # 趋势筛选
            t_dept = st.selectbox("分析部门", full_df['Dept'].unique(), key='t2_dept')
        with cc2:
            t_data = full_df[full_df['Dept'] == t_dept]
            t_prov = st.selectbox("分析服务商", t_data['Provider'].unique(), key='t2_prov')
            
        t_final = t_data[t_data['Provider'] == t_prov]
        
        # 仓库细分
        t_wh_list = sorted(t_final['Warehouse'].astype(str).unique().tolist())
        t_wh_list.insert(0, "全部汇总")
        t_wh = st.selectbox("分析仓库 (可选)", t_wh_list, key='t2_wh')
        
        if t_wh != "全部汇总":
            trend_source = t_final[t_final['Warehouse'] == t_wh]
        else:
            trend_source = t_final
            
        if len(trend_source['Date'].unique()) < 2:
            st.warning("⚠️ 当前筛选的数据只有一个月份，无法展示趋势。请上传更多月份的文件。")
        else:
            # 数据聚合：按日期分组
            trend_agg = trend_source.groupby('Date').agg({
                'Fee': 'sum',
                'Vol': 'sum',
                'Qty': 'sum'
            }).reset_index().sort_values('Date')
            
            # 1. 费用 & 体积 双轴趋势图
            st.markdown("##### 💰 费用(Bar) 与 体积(Line) 变化")
            
            # 使用简单的 Streamlit 图表 (也可换成 Altair 更高级)
            chart_data = trend_agg.set_index('Date')[['Fee', 'Vol']]
            st.bar_chart(chart_data['Fee'], color='#FF4B4B') # 红色柱状表示费用
            st.line_chart(chart_data['Vol'], color='#0000FF') # 蓝色线表示体积
            
            # 2. 呆滞库存 (360天+) 趋势
            st.markdown("##### ⚠️ 360天+ 极度呆滞库存趋势")
            dead_stock = trend_source[trend_source['Age_Range'] == '360天+']
            if dead_stock.empty:
                st.success("该时间段内无 360天+ 呆滞库存！")
            else:
                dead_trend = dead_stock.groupby('Date')['Fee'].sum().reset_index().sort_values('Date')
                st.area_chart(dead_trend.set_index('Date'), color='#808080')
            
            # 3. 数据透视表
            st.markdown("##### 📋 详细数据对比")
            pivot = trend_agg.set_index('Date').T
            st.dataframe(pivot.style.format("{:,.2f}"), use_container_width=True)