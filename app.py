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

def load_data_v4(file):
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
st.set_page_config(page_title="海外仓库存 BI V4.0", page_icon="🌍", layout="wide")
st.title("🌍 海外仓库存分析看板 V4.0 (上帝视角版)")

with st.expander("ℹ️ 文件命名规范", expanded=False):
    st.markdown("请将文件重命名为：**`部门_服务商_日期.xlsx`** (例如: `业务一部_AI_2024-01.xlsx`)")

# --- 侧边栏 ---
with st.sidebar:
    st.header("📂 数据中心")
    uploaded_files = st.file_uploader("批量上传文件", type=['xlsx', 'xls', 'csv'], accept_multiple_files=True)
    
    dfs = []
    if uploaded_files:
        for file in uploaded_files:
            df = load_data_v4(file)
            if not df.empty:
                dfs.append(df)
        st.success(f"已加载 {len(dfs)} 个文件")

if not dfs:
    st.info("👈 请上传数据文件以开始分析")
else:
    full_df = pd.concat(dfs, ignore_index=True)
    
    tab1, tab2 = st.tabs(["📊 全景详情 (SKU级)", "🆚 历史趋势 & 风险洞察"])
    
    # ================= TAB 1: 全景详情 (三级全汇总) =================
    with tab1:
        # --- 1. 部门选择 ---
        # 逻辑：先拿出所有部门，前面加一个“全部汇总”
        all_depts = sorted(full_df['Dept'].unique().tolist())
        all_depts.insert(0, "全部汇总")
        
        c1, c2, c3, c4 = st.columns(4)
        with c1: 
            sel_dept = st.selectbox("① 选择部门", all_depts, key='t1_d')
            
        # 根据部门筛选数据池 (Level 1 Filter)
        if sel_dept == "全部汇总":
            df_l1 = full_df
        else:
            df_l1 = full_df[full_df['Dept'] == sel_dept]

        # --- 2. 日期选择 ---
        # 逻辑：日期一般是单选，为了看特定月份的报表
        avail_dates = sorted(df_l1['Date'].unique(), reverse=True)
        with c2: 
            sel_date = st.selectbox("② 选择月份", avail_dates, key='t1_dt')
            
        # 根据日期筛选数据池 (Time Filter)
        df_l2 = df_l1[df_l1['Date'] == sel_date]

        # --- 3. 服务商选择 ---
        # 逻辑：基于当前剩下的数据，看有哪些服务商
        avail_provs = sorted(df_l2['Provider'].unique().tolist())
        avail_provs.insert(0, "全部汇总")
        with c3: 
            sel_prov = st.selectbox("③ 选择服务商", avail_provs, key='t1_p')
            
        # 根据服务商筛选数据池 (Level 2 Filter)
        if sel_prov == "全部汇总":
            df_l3 = df_l2
        else:
            df_l3 = df_l2[df_l2['Provider'] == sel_prov]
            
        # --- 4. 仓库选择 ---
        # 逻辑：基于当前剩下的数据，看有哪些仓库
        avail_whs = sorted(df_l3['Warehouse'].astype(str).unique().tolist())
        avail_whs.insert(0, "全部汇总")
        with c4: 
            sel_wh = st.selectbox("④ 选择仓库", avail_whs, key='t1_w')
            
        # 最终数据 (Final Filter)
        if sel_wh == "全部汇总":
            final_df = df_l3
        else:
            final_df = df_l3[df_l3['Warehouse'] == sel_wh]
            
        # ---------------- 页面展示 ----------------
        
        # 标题动态显示
        st.markdown(f"### 📋 数据视图：{sel_dept} · {sel_prov} · {sel_wh}")

        # 统计 KPI
        k1, k2, k3 = st.columns(3)
        k1.metric("总库存 (Qty)", f"{final_df['Qty'].sum():,.0f}")
        k2.metric("总体积 (Vol)", f"{final_df['Vol'].sum():,.2f} m³")
        k3.metric("总费用 (Fee)", f"${final_df['Fee'].sum():,.2f}")
        
        # 库龄结构表
        summary = final_df.groupby('Age_Range').agg({'Fee':'sum','Qty':'sum','Vol':'sum'}).reset_index()
        order_map = {l: i for i, l in enumerate(AGE_LABELS)}
        summary['sort'] = summary['Age_Range'].map(order_map).fillna(999)
        summary = summary.sort_values('sort').drop('sort', axis=1)
        summary['费用占比'] = (summary['Fee']/final_df['Fee'].sum()*100).fillna(0)
        
        st.dataframe(summary.style.format({'Fee':'${:.2f}','费用占比':'{:.1f}%'}), use_container_width=True)
        
        # Top 20 深钻
        st.divider()
        st.markdown("#### 🔍 异常库存深钻")
        
        valid_ages = [l for l in AGE_LABELS if l in final_df['Age_Range'].unique()]
        if valid_ages:
            r_col1, r_col2 = st.columns([3, 1])
            with r_col1:
                rng = st.radio("选择库龄段", valid_ages, horizontal=True, index=len(valid_ages)-1, key='t1_r')
            
            drill = final_df[final_df['Age_Range'] == rng].copy()
            
            # 判断是否开启聚合：只要部门、服务商、仓库任一选了“全部”，就可以开启聚合
            is_any_all_selected = (sel_dept == "全部汇总") or (sel_prov == "全部汇总") or (sel_wh == "全部汇总")
            
            show_agg = False
            if is_any_all_selected:
                with r_col2:
                    st.write("")
                    st.write("") 
                    # 动态文案
                    help_text = "将同一 SKU 的数据合并显示（费用叠加）。"
                    show_agg = st.checkbox("🔀 SKU 宏观聚合", value=True, help=help_text, key="chk_agg_mode")
            
            if drill.empty:
                st.info("无数据")
            else:
                if show_agg:
                    try:
                        # 强转数字防止报错
                        for col in ['Qty', 'Vol', 'Fee', 'Age']:
                            drill[col] = pd.to_numeric(drill[col], errors='coerce').fillna(0)
                        
                        # 1. 聚合 (注意：如果选了全部部门，这里会把不同部门的同SKU也加上)
                        agg_sku = drill.groupby('SKU').agg({
                            'Qty': 'sum',
                            'Vol': 'sum',
                            'Fee': 'sum',
                            'Age': 'mean',
                            'Warehouse': 'nunique',
                            'Dept': 'nunique',     # 统计涉及几个部门
                            'Provider': 'nunique'  # 统计涉及几个服务商
                        }).reset_index()
                        
                        top20 = agg_sku.sort_values('Fee', ascending=False).head(20)
                        
                        # 构建描述信息
                        def build_info(row):
                            infos = []
                            if sel_dept == "全部汇总" and row['Dept'] > 1: infos.append(f"{row['Dept']}个部门")
                            if sel_prov == "全部汇总" and row['Provider'] > 1: infos.append(f"{row['Provider']}个服务商")
                            infos.append(f"{row['Warehouse']}个仓")
                            return " | ".join(infos)

                        top20['分布'] = top20.apply(build_info, axis=1)
                        
                        top20_show = top20[['SKU', '分布', 'Qty', 'Vol', 'Fee', 'Age']].copy()
                        top20_show.columns = ['SKU', '分布情况', '总库存', '总体积', '总费用(叠加)', '平均库龄']
                        
                        st.success(f"📊 宏观视角已开启：正在查看 **{sel_dept}** - **{sel_prov}** 范围内的 SKU 综合表现。")
                        
                        st.dataframe(
                            top20_show.style.format({
                                '总费用(叠加)': '${:.2f}', 
                                '平均库龄': '{:.0f}',
                                '总体积': '{:.2f}'
                            }).background_gradient(subset=['总费用(叠加)'], cmap='Reds'), 
                            use_container_width=True
                        )
                    except Exception as e:
                        st.error(f"聚合计算出错: {str(e)}")
                        st.dataframe(drill.head(20))
                else:
                    # 原始明细模式
                    cols_show = ['SKU', 'Warehouse', 'Qty', 'Vol', 'Fee', 'Age']
                    # 如果选了全部部门，最好把部门和服务商也展示出来
                    if sel_dept == "全部汇总": cols_show.insert(1, 'Dept')
                    if sel_prov == "全部汇总": cols_show.insert(2, 'Provider')
                    
                    top20 = drill.sort_values('Fee', ascending=False).head(20)[cols_show]
                    try:
                        st.dataframe(top20.style.format({'Fee':'${:.2f}', 'Vol': '{:.2f}'}).background_gradient(subset=['Fee'], cmap='Reds'), use_container_width=True)
                    except:
                        st.dataframe(top20, use_container_width=True)
        else:
            st.warning("无数据")

    # ================= TAB 2: 趋势对比 (适配全景逻辑) =================
    with tab2:
        st.markdown("#### 🆚 历史趋势 & 风险洞察")
        
        # 同样的级联逻辑
        cc1, cc2, cc3 = st.columns(3)
        
        # 1. 部门
        all_depts_t = sorted(full_df['Dept'].unique().tolist())
        all_depts_t.insert(0, "全部汇总")
        with cc1: t_dept = st.selectbox("分析部门", all_depts_t, key='t2_d')
        
        df_t1 = full_df if t_dept == "全部汇总" else full_df[full_df['Dept'] == t_dept]

        # 2. 服务商
        all_provs_t = sorted(df_t1['Provider'].unique().tolist())
        all_provs_t.insert(0, "全部汇总")
        with cc2: t_prov = st.selectbox("分析服务商", all_provs_t, key='t2_p')
        
        df_t2 = df_t1 if t_prov == "全部汇总" else df_t1[df_t1['Provider'] == t_prov]

        # 3. 仓库
        all_whs_t = sorted(df_t2['Warehouse'].astype(str).unique().tolist())
        all_whs_t.insert(0, "全部汇总")
        with cc3: t_wh = st.selectbox("分析仓库", all_whs_t, key='t2_w')
        
        t_final = df_t2 if t_wh == "全部汇总" else df_t2[df_t2['Warehouse'] == t_wh]
        
        # --- 下面的图表逻辑不需要变，因为 t_final 已经是筛选好的了 ---
        available_dates = sorted(t_final['Date'].unique())
        selected_dates = st.multiselect("选择分析月份", available_dates, default=available_dates)
        
        if not selected_dates:
            st.warning("请选择月份。")
        else:
            chart_df = t_final[t_final['Date'].isin(selected_dates)]
            
            # KPI
            st.divider()
            latest_month = sorted(selected_dates)[-1]
            latest_data = t_final[t_final['Date'] == latest_month]
            
            dead_fee = latest_data[latest_data['Age_Range'] == '360天+']['Fee'].sum()
            total_fee = latest_data['Fee'].sum()
            total_qty = latest_data['Qty'].sum()
            cpu = total_fee / total_qty if total_qty > 0 else 0
            
            kp1, kp2, kp3 = st.columns(3)
            kp1.metric(f"{latest_month} 总仓租", f"${total_fee:,.0f}")
            kp2.metric(f"📉 单位仓租成本", f"${cpu:.3f} /件")
            kp3.metric(f"💰 360天+潜在节省", f"${dead_fee:,.0f}")
            
            st.divider()

            # 图表
            agg_df = chart_df.groupby(['Date', 'Age_Range']).agg({
                'Qty': 'sum', 'Fee': 'sum', 'Vol': 'sum'
            }).reset_index()
            
            st.markdown("##### 📦 各库龄段库存量对比")
            base_chart = alt.Chart(agg_df).encode(
                x=alt.X('Age_Range', sort=AGE_LABELS, title="库龄分段"),
                y=alt.Y('Qty', title="库存数量"),
                color=alt.Color('Date', title="月份"),
                tooltip=['Date', 'Age_Range', 'Qty']
            )
            grouped_bar = base_chart.mark_bar().encode(xOffset='Date').properties(height=350)
            st.altair_chart(grouped_bar, use_container_width=True)
            
            c_fee, c_cpu = st.columns(2)
            with c_fee:
                st.markdown("##### 💰 费用结构")
                fee_pivot = agg_df.pivot(index='Date', columns='Age_Range', values='Fee')
                sorted_cols = [c for c in AGE_LABELS if c in fee_pivot.columns]
                st.bar_chart(fee_pivot[sorted_cols])
            
            with c_cpu:
                st.markdown("##### 📉 单位仓租成本趋势")
                cpu_trend = chart_df.groupby('Date').apply(
                    lambda x: pd.Series({'CPU': x['Fee'].sum() / x['Qty'].sum() if x['Qty'].sum() > 0 else 0})
                ).reset_index()
                
                cpu_chart = alt.Chart(cpu_trend).mark_line(point=True).encode(
                    x='Date',
                    y=alt.Y('CPU', title='单件成本 ($)'),
                    tooltip=['Date', alt.Tooltip('CPU', format='.3f')]
                ).properties(height=300)
                st.altair_chart(cpu_chart, use_container_width=True)

            # 恶化预警
            st.divider()
            st.markdown("#### 🚨 库存恶化监控")
            if len(selected_dates) >= 2:
                sorted_dates = sorted(selected_dates)
                curr_month = sorted_dates[-1]
                prev_month = sorted_dates[-2]
                
                # 聚合时需包含 Dept 和 Provider 防止 SKU 重复
                group_cols = ['SKU', 'Warehouse', 'Dept', 'Provider']
                
                df_curr = chart_df[chart_df['Date'] == curr_month][group_cols + ['Age_Range', 'Fee']]
                df_prev = chart_df[chart_df['Date'] == prev_month][group_cols + ['Age_Range']]
                
                merged = pd.merge(df_prev, df_curr, on=group_cols, suffixes=('_old', '_new'))
                merged['idx_old'] = merged['Age_Range_old'].map(AGE_MAP).fillna(-1)
                merged['idx_new'] = merged['Age_Range_new'].map(AGE_MAP).fillna(-1)
                
                worsened = merged[merged['idx_new'] > merged['idx_old']].copy()
                
                if worsened.empty:
                    st.success("🎉 无库存恶化。")
                else:
                    worsened['Fee'] = worsened['Fee'].astype(float)
                    top_worsened = worsened.sort_values('Fee', ascending=False).head(20)
                    
                    st.dataframe(
                        top_worsened[['SKU', 'Dept', 'Warehouse', 'Age_Range_old', 'Age_Range_new', 'Fee']]
                        .rename(columns={'Age_Range_old': f'{prev_month} 库龄', 'Age_Range_new': f'{curr_month} 库龄', 'Fee': '当前仓租($)'})
                        .style.format({'当前仓租($)': '${:.2f}'})
                        .background_gradient(subset=['当前仓租($)'], cmap='Reds'),
                        use_container_width=True
                    )
            else:
                st.info("💡 请选择至少 2 个月份以启用恶化监控。")