import pandas as pd
import itertools

def divide_groups(df, max_group_size=5):

    all_results = []
    ca_groups = df['Ca học'].unique()
    html_summaries = []

    for ca in ca_groups:
        ca_df = df[df['Ca học'] == ca].copy().reset_index(drop=True)
        n_students = len(ca_df)
        n_groups = (n_students + max_group_size - 1) // max_group_size

        ca_df = ca_df.sort_values('Điểm tổng', ascending=False).reset_index(drop=True)
        groups = [[] for _ in range(n_groups)]
        for i, (_, row) in enumerate(ca_df.iterrows()):
            groups[i % n_groups].append(row)
        groups = [pd.DataFrame(g).reset_index(drop=True) for g in groups]

        for g in groups:
            leaders = g[g['Vai trò mong muốn'].str.contains('Nhóm trưởng', na=False)]
            g.attrs['Truong'] = leaders.iloc[0]['Họ tên'] if len(leaders) > 0 else g.loc[g['Điểm tổng'].idxmax(), 'Họ tên']

        improved = True
        max_iter = 500
        iter_count = 0

        group_scores = [g['Điểm tổng'].values.copy() for g in groups]

        while improved and iter_count < max_iter:
            iter_count += 1
            improved = False
            avg_scores = [scores.mean() for scores in group_scores]
            max_idx = avg_scores.index(max(avg_scores))
            min_idx = avg_scores.index(min(avg_scores))
            max_group = groups[max_idx]
            min_group = groups[min_idx]
            max_scores = group_scores[max_idx]
            min_scores = group_scores[min_idx]

            best_score = max(avg_scores) - min(avg_scores)
            best_swap = None

            for i, s_max in enumerate(max_scores):
                for j, s_min in enumerate(min_scores):
                    temp_max_scores = max_scores.copy()
                    temp_min_scores = min_scores.copy()
                    temp_max_scores[i], temp_min_scores[j] = s_min, s_max

                    new_avg_scores = avg_scores.copy()
                    new_avg_scores[max_idx] = temp_max_scores.mean()
                    new_avg_scores[min_idx] = temp_min_scores.mean()
                    new_diff = max(new_avg_scores) - min(new_avg_scores)

                    skills_max = set(max_group['Điểm mạnh'].iloc[i].split("; ")) if pd.notna(max_group['Điểm mạnh'].iloc[i]) else set()
                    skills_min = set(min_group['Điểm mạnh'].iloc[j].split("; ")) if pd.notna(min_group['Điểm mạnh'].iloc[j]) else set()
                    temp_max_skills = set(itertools.chain.from_iterable(
                        [s.split("; ") for k, s in max_group['Điểm mạnh'].items() if k != i and isinstance(s, str)]
                    )).union(skills_min)
                    temp_min_skills = set(itertools.chain.from_iterable(
                        [s.split("; ") for k, s in min_group['Điểm mạnh'].items() if k != j and isinstance(s, str)]
                    )).union(skills_max)

                    skill_div = len(temp_max_skills) + len(temp_min_skills)
                    score = new_diff - 0.01*skill_div

                    if score < best_score:
                        best_score = score
                        best_swap = (i, j)

            if best_swap is not None:
                i, j = best_swap
                tmp_row = max_group.loc[i].copy()
                max_group.loc[i] = min_group.loc[j]
                min_group.loc[j] = tmp_row

                max_scores[i], min_scores[j] = min_scores[j], max_scores[i]

                group_scores[max_idx] = max_scores
                group_scores[min_idx] = min_scores

                improved = True

                for g in [max_group, min_group]:
                    leaders = g[g['Vai trò mong muốn'].str.contains('Nhóm trưởng', na=False)]
                    g.attrs['Truong'] = leaders.iloc[0]['Họ tên'] if len(leaders) > 0 else g.loc[g['Điểm tổng'].idxmax(), 'Họ tên']

        html = f"<h4>===== CA: {ca} | Số nhóm = {len(groups)} =====</h4>"
        for idx, g in enumerate(groups, 1):
            g.attrs['Ca'] = ca
            avg_score_val = g['Điểm tổng'].mean()
            leaders_count = g['Vai trò mong muốn'].str.contains('Nhóm trưởng', na=False).sum()
            goals = g['Mục tiêu'].value_counts().to_dict()
            skills_set = set()
            for s in g['Điểm mạnh']:
                if isinstance(s,str):
                    for part in s.split(";"):
                        skills_set.add(part.strip())

            html += f"""
            <div style='margin:15px 0;padding:10px;border:1px solid #ccc;'>
                <b>Nhóm {idx}:</b> n={len(g)} | Điểm TB = {avg_score_val:.2f} | Leaders = {leaders_count}<br>
                <i>Mục tiêu:</i> {goals}<br>
                <i>Kỹ năng có:</i> {skills_set}<br>
            """

            df_print = g.reset_index(drop=True).copy()
            show_cols = ["STT","MSSV","Họ tên","GPA","Điểm ĐTĐM","Điểm tổng",
                        "Vai trò mong muốn","Mục tiêu","Điểm mạnh"]
            show_cols = [c for c in show_cols if c in df_print.columns]

            html += df_print[show_cols].to_html(index=False, escape=False)
            html += "</div>"

        all_results.extend(groups)
        html_summaries.append(html)

    return html_summaries, all_results
