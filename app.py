import streamlit as st
import pandas as pd
import io
import altair as alt

# ================= 1. 配置与映射 =================
COLUMN_MAPS = {
    'WP': { 
        'SKU': 'SKU', 'Warehouse': '仓库/Warehouse', 
        'Qty': '数量/Quantity', 'Fee': '金额/Amount', 
        'Age': '库龄/Library of Age', 'Vol': '体积(m³)',
        'Full_Name': 'WesternPost'
    },
    'LG': { 
        'SKU': '乐仓货品编码', 'Warehouse': '仓库', 
        'Qty': '数量', 'Fee': '计算金额', 
        'Age': '库龄', 'Vol': '总体积',
        'Full_Name': 'Lecangs'
    },
    'AI': { 
        'SKU': 'SKU', 'Warehouse': '仓库', 
        'Qty': '库存', 'Fee': '费用', 
        'Age': '在库天数', 'Vol': '立方数',
        'Full_Name': 'AI'
    },
    'WL': { 
        'SKU': '商品SKU', 'Warehouse': '实际发货仓库', 
        'Qty': '库存总数_QTY', 'Fee': '计费总价', 
        'Age': '库存库龄_CD', 'Vol': '计费总体积_立方米',
        'Full_Name': 'WWL'
    }
}

AGE_BINS = [0, 30, 60, 90, 120, 180, 360, 99999]
AGE_LABELS = ['0-30天', '31-60天', '61-90天', '91-120天', '120-180天', '180-360天', '360天+']
# 建立库龄的数字索引，用于比较"恶化" (0=0-30天, 6=360天+)
AGE_MAP = {label: i for i, label in enumerate(AGE_LABELS)}

# ================= 2. 核心处理逻辑 =================

def parse_filename(filename):
    name_body = filename.rsplit('.', 1)[0]
    parts = name_body.split('_')
    
    if len(parts) >= 3:
        dept = parts[0]
        raw_code = parts[1].upper()
        provider_code = None
        for key in COLUMN_MAPS.keys():
            if key in raw_code:
                provider_code = key
                break
        date_str = parts[2]
        return dept, provider_code, date_str
    return None, None, None

def load_data_v1_1(file):
    # 1. 解析文件名
    dept, provider_code, date_str = parse_filename(file.name)
    
    if not dept:
        dept = "默认部门"
        for code in COLUMN_MAPS.keys():
            if code in file.name.upper():
                provider_code = code
                break
        date_str = "最新"

    if not provider_code:
        st.toast(f"⚠️ 跳过未知文件: {file.name}", icon="⏭️")
        return pd.DataFrame()

    # 2. 读取文件
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
        
        # 3. 智能表头定位
        header_idx = 0
        expected_cols = set(mapping.values())
        expected_cols.discard(mapping.get('Full_Name'))
        
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

        # 4. 清洗
        valid_map = {k: v for k, v in mapping.items() if v in df.columns}
        rename_dict = {v: k for k, v in valid_map.items()}
        df = df.rename(columns=rename_dict)
        
        required_cols = ['SKU', 'Warehouse', 'Qty', 'Fee', 'Age', 'Vol']
        for col in required_cols:
            if col not in df.columns: df[col] = 0 
                
        for col in ['Qty', 'Fee', 'Age', 'Vol']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        cut_series = pd.cut(df['Age'], bins=AGE_BINS, labels=AGE_LABELS, right=False)
        df['Age_Range'] = cut_series.astype(str)
        df.loc[df['Age_Range'] == 'nan', 'Age_Range'] = '360天+'
        df['Age_Range'] = df['Age_Range'].str.strip()

        df['Dept'] = dept
        df['Provider'] = mapping['Full_Name']
        df['Date'] = date_str
        
        return df
        
    except Exception as e:
        return pd.DataFrame()

# ================= 3. 界面逻辑 =================
st.set_page_config(page_title="海外仓库存 BI V1.1", page_icon="📈", layout="wide")
st.title("📈 海外仓库存分析看板 V1.1 (管理增强版)")

with st.expander("ℹ️ 文件命名规范", expanded=False):
    st.markdown("请将文件重命名为：**`部门_服务商_日期.xlsx`** (例如: `业务一部_AI_2024-01.xlsx`)")

# --- 侧边栏 ---
with st.sidebar:
    st.header("📂 数据中心")
    uploaded_files = st.file_uploader("批量上传文件", type=['xlsx', 'xls', 'csv'], accept_multiple_files=True)
    
    dfs = []
    if uploaded_files:
        for file in uploaded_files:
            df = load_data_v1_1(file)
            if not df.empty:
                dfs.append(df)
        st.success(f"已加载 {len(dfs)} 个文件")

if not dfs:
    st.info("👈 请上传数据文件以开始分析")
else:
    full_df = pd.concat(dfs, ignore_index=True)
    
    tab1, tab2 = st.tabs(["📊 单月详情 (SKU级)", "🆚 历史趋势 & 风险洞察"])
    
    # ================= TAB 1: 详情分析 =================
    with tab1:
        c1, c2, c3 = st.columns(3)
        with c1: sel_dept = st.selectbox("选择部门", full_df['Dept'].unique(), key='t1_d')
        with c2: sel_date = st.selectbox("选择月份", sorted(full_df[full_df['Dept']==sel_dept]['Date'].unique(), reverse=True), key='t1_dt')
        with c3: sel_prov = st.selectbox("选择服务商", full_df[(full_df['Dept']==sel_dept)&(full_df['Date']==sel_date)]['Provider'].unique(), key='t1_p')
            
        target_df = full_df[(full_df['Dept']==sel_dept)&(full_df['Date']==sel_date)&(full_df['Provider']==sel_prov)]
        
        wh_list = sorted(target_df['Warehouse'].astype(str).unique().tolist())
        wh_list.insert(0, "全部汇总")
        sel_wh = st.selectbox("选择仓库", wh_list, key='t1_w')
        
        final_df = target_df if sel_wh == "全部汇总" else target_df[target_df['Warehouse'] == sel_wh]
        
        # 统计
        k1, k2, k3 = st.columns(3)
        k1.metric("总库存", f"{final_df['Qty'].sum():,.0f}")
        k2.metric("总体积", f"{final_df['Vol'].sum():,.2f} m³")
        k3.metric("总费用", f"${final_df['Fee'].sum():,.2f}")
        
        # 库龄表
        summary = final_df.groupby('Age_Range').agg({'Fee':'sum','Qty':'sum','Vol':'sum'}).reset_index()
        order_map = {l: i for i, l in enumerate(AGE_LABELS)}
        summary['sort'] = summary['Age_Range'].map(order_map).fillna(999)
        summary = summary.sort_values('sort').drop('sort', axis=1)
        summary['费用占比'] = (summary['Fee']/final_df['Fee'].sum()*100).fillna(0)
        
        st.dataframe(summary.style.format({'Fee':'${:.2f}','费用占比':'{:.1f}%'}), use_container_width=True)
        
        # Top 20
        st.divider()
        st.markdown("#### 🔍 异常库存深钻")
        valid_ages = [l for l in AGE_LABELS if l in final_df['Age_Range'].unique()]
        if valid_ages:
            rng = st.radio("选择库龄段", valid_ages, horizontal=True, index=len(valid_ages)-1, key='t1_r')
            drill = final_df[final_df['Age_Range'] == rng]
            if not drill.empty:
                top20 = drill.sort_values('Fee', ascending=False).head(20)[['SKU','Warehouse','Qty','Vol','Fee','Age']]
                try:
                    st.dataframe(top20.style.format({'Fee':'${:.2f}'}).background_gradient(subset=['Fee'], cmap='Reds'), use_container_width=True)
                except:
                    st.dataframe(top20, use_container_width=True)
            else: st.info("无数据")
        else: st.warning("无数据")

    # ================= TAB 2: 趋势对比 & 管理洞察 =================
    with tab2:
        st.markdown("#### 🆚 历史趋势 & 风险洞察")
        
        cc1, cc2, cc3 = st.columns(3)
        with cc1: t_dept = st.selectbox("分析部门", full_df['Dept'].unique(), key='t2_d')
        with cc2: t_prov = st.selectbox("分析服务商", full_df[full_df['Dept']==t_dept]['Provider'].unique(), key='t2_p')
        
        t_base = full_df[(full_df['Dept']==t_dept)&(full_df['Provider']==t_prov)]
        
        t_wh_list = sorted(t_base['Warehouse'].astype(str).unique().tolist())
        t_wh_list.insert(0, "全部汇总")
        with cc3: t_wh = st.selectbox("分析仓库", t_wh_list, key='t2_w')
        
        t_final = t_base if t_wh == "全部汇总" else t_base[t_base['Warehouse']==t_wh]
        
        available_dates = sorted(t_final['Date'].unique())
        selected_dates = st.multiselect("选择分析月份 (建议选2-3个)", available_dates, default=available_dates)
        
        if not selected_dates:
            st.warning("请选择月份。")
        else:
            # 数据准备
            chart_df = t_final[t_final['Date'].isin(selected_dates)]
            
            # --- 模块 A: 核心 KPI 仪表盘 (新增：节省计算 & 单位成本) ---
            st.divider()
            latest_month = sorted(selected_dates)[-1]
            latest_data = t_final[t_final['Date'] == latest_month]
            
            # 1. 计算呆滞节省金额
            dead_fee = latest_data[latest_data['Age_Range'] == '360天+']['Fee'].sum()
            
            # 2. 计算单位仓租成本 (CPU)
            total_fee = latest_data['Fee'].sum()
            total_qty = latest_data['Qty'].sum()
            cpu = total_fee / total_qty if total_qty > 0 else 0
            
            kp1, kp2, kp3 = st.columns(3)
            kp1.metric(f"{latest_month} 单日仓租", f"${total_fee:,.0f}")
            kp2.metric(f"📉 单位仓租成本 (CPU)", f"${cpu:.3f} /件")
            kp3.metric(f"💰 清理360天+潜在节省", f"${dead_fee:,.0f}", help="如果现在清理掉所有360天+的库存，下个月能省下的仓租")
            
            st.divider()

            # --- 模块 B: 图表分析 ---
            agg_df = chart_df.groupby(['Date', 'Age_Range']).agg({
                'Qty': 'sum', 'Fee': 'sum', 'Vol': 'sum'
            }).reset_index()
            
            # 1. 库存结构对比 (簇状柱形图)
            st.markdown("##### 📦 各库龄段库存量对比 (Quantity Structure)")
            base_chart = alt.Chart(agg_df).encode(
                x=alt.X('Age_Range', sort=AGE_LABELS, title="库龄分段"),
                y=alt.Y('Qty', title="库存数量"),
                color=alt.Color('Date', title="月份"),
                tooltip=['Date', 'Age_Range', 'Qty']
            )
            grouped_bar = base_chart.mark_bar().encode(xOffset='Date').properties(height=350)
            st.altair_chart(grouped_bar, use_container_width=True)
            
            # 2. 费用趋势 & 单位成本趋势 (新增)
            c_fee, c_cpu = st.columns(2)
            with c_fee:
                st.markdown("##### 💰 费用结构 (Fee Structure)")
                fee_pivot = agg_df.pivot(index='Date', columns='Age_Range', values='Fee')
                sorted_cols = [c for c in AGE_LABELS if c in fee_pivot.columns]
                st.bar_chart(fee_pivot[sorted_cols])
            
            with c_cpu:
                st.markdown("##### 📉 单位仓租成本趋势 (Cost Per Unit)")
                # 计算每个月的 CPU
                cpu_trend = chart_df.groupby('Date').apply(
                    lambda x: pd.Series({'CPU': x['Fee'].sum() / x['Qty'].sum() if x['Qty'].sum() > 0 else 0})
                ).reset_index()
                
                cpu_chart = alt.Chart(cpu_trend).mark_line(point=True).encode(
                    x='Date',
                    y=alt.Y('CPU', title='单件成本 ($)'),
                    tooltip=['Date', alt.Tooltip('CPU', format='.3f')]
                ).properties(height=300)
                st.altair_chart(cpu_chart, use_container_width=True)

            # --- 模块 C: 恶化预警雷达 (新增) ---
            st.divider()
            st.markdown("#### 🚨 风险预警：库存恶化监控 (The Drifters)")
            st.caption("这里展示那些 **库龄段变差** 的 SKU。它们正在变老，如果不处理，就会变成死库存。")
            
            if len(selected_dates) >= 2:
                # 默认比较最近的两个月
                sorted_dates = sorted(selected_dates)
                curr_month = sorted_dates[-1]
                prev_month = sorted_dates[-2]
                
                c_d1, c_d2 = st.columns([1, 3])
                with c_d1:
                    st.info(f"正在对比: \n\n **{prev_month}** (旧) \n 🆚 \n **{curr_month}** (新)")
                
                with c_d2:
                    # 提取数据
                    df_curr = chart_df[chart_df['Date'] == curr_month][['SKU', 'Warehouse', 'Age_Range', 'Fee']]
                    df_prev = chart_df[chart_df['Date'] == prev_month][['SKU', 'Warehouse', 'Age_Range']]
                    
                    # 合并对比
                    merged = pd.merge(df_prev, df_curr, on=['SKU', 'Warehouse'], suffixes=('_old', '_new'))
                    
                    # 计算库龄等级 (0-6)
                    merged['idx_old'] = merged['Age_Range_old'].map(AGE_MAP).fillna(-1)
                    merged['idx_new'] = merged['Age_Range_new'].map(AGE_MAP).fillna(-1)
                    
                    # 筛选恶化: 新等级 > 旧等级
                    worsened = merged[merged['idx_new'] > merged['idx_old']].copy()
                    
                    if worsened.empty:
                        st.success("🎉 太棒了！没有发现 SKU 库龄恶化的情况。")
                    else:
                        worsened['Fee'] = worsened['Fee'].astype(float)
                        # 按当前费用倒序，抓大头
                        top_worsened = worsened.sort_values('Fee', ascending=False).head(20)
                        
                        st.dataframe(
                            top_worsened[['SKU', 'Warehouse', 'Age_Range_old', 'Age_Range_new', 'Fee']]
                            .rename(columns={
                                'Age_Range_old': f'{prev_month} 库龄',
                                'Age_Range_new': f'{curr_month} 库龄 (恶化)',
                                'Fee': '当前仓租($)'
                            })
                            .style.format({'当前仓租($)': '${:.2f}'})
                            .background_gradient(subset=['当前仓租($)'], cmap='Reds'),
                            use_container_width=True
                        )
            else:
                st.info("💡 请至少选择 2 个月份来开启【恶化监控】功能。")