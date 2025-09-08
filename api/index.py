from flask import Flask, request, jsonify, send_from_directory
import pandas as pd
import io
import re

app = Flask(__name__)

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/api/aggregate', methods=['POST'])
def aggregate_uploaded_files():
    """
    複数のアップロードされたCSVファイルから、品種ごとの合計分量を集計します。
    """
    uploaded_files = request.files.getlist('csv_files')
    # 集計したい品種を定義
    varieties = ['つや姫', 'はえぬき', '雪若丸', '佐藤錦', '紅秀峰']
    combined_results_df = pd.DataFrame(columns=['品種', '分量_kg'])

    for file in uploaded_files:
        try:
            # 修正前
            # df = pd.read_csv(io.StringIO(file.stream.read().decode('cp932')))

            # 修正後
            try:
                # まずはutf-8でデコードを試みる
                file_content = file.stream.read().decode('utf-8')
                df = pd.read_csv(io.StringIO(file_content))
            except UnicodeDecodeError:
                # 失敗した場合はcp932で再試行
                file.stream.seek(0) # ストリームの位置をリセット
                file_content = file.stream.read().decode('cp932')
                df = pd.read_csv(io.StringIO(file_content))

            # 必要な列がない場合はスキップ
            if '商品名' not in df.columns:
                print(f"'{file.filename}'：'商品名'列が見つかりません。スキップします。")
                continue

            current_file_results = pd.DataFrame(columns=['品種', '分量_kg'])
            
            # 数量列と分量列の存在を確認
            has_quantity = '数量' in df.columns
            has_amount = '分量' in df.columns

            if has_amount:
                # 分量列がある場合
                df['分量_kg'] = df['分量'].apply(
                    lambda amount_str: 
                        float(re.search(r'(\d+\.?\d*)\s*(kg|g)', str(amount_str), re.IGNORECASE).group(1)) / 1000 
                        if re.search(r'(\d+\.?\d*)\s*(kg|g)', str(amount_str), re.IGNORECASE) and re.search(r'(\d+\.?\d*)\s*(kg|g)', str(amount_str), re.IGNORECASE).group(2).lower() == 'g'
                        else float(re.search(r'(\d+\.?\d*)\s*(kg|g)', str(amount_str), re.IGNORECASE).group(1))
                        if re.search(r'(\d+\.?\d*)\s*(kg|g)', str(amount_str), re.IGNORECASE)
                        else 0.0
                )
                if has_quantity:
                    df['数量'] = pd.to_numeric(df['数量'], errors='coerce').fillna(0)
                else:
                    df['数量'] = 1
                
                df['総分量'] = df['分量_kg'] * df['数量']
                df['品種'] = df['商品名'].apply(
                    lambda x: next((v for v in varieties if v in str(x)), None)
                )
                filtered_df = df.dropna(subset=['品種'])
                
                if not filtered_df.empty:
                    file_agg = filtered_df.groupby('品種')['総分量'].sum().reset_index()
                    file_agg.rename(columns={'総分量': '分量_kg'}, inplace=True)
                    current_file_results = file_agg
            
            else:
                # 分量列がなく、商品名から分量を抽出する場合
                if has_quantity:
                    df['数量'] = pd.to_numeric(df['数量'], errors='coerce').fillna(0)
                else:
                    df['数量'] = 1
                results_list = []
                for _, row in df.iterrows():
                    product_name = str(row['商品名'])
                    
                    set_match = re.search(r'各(\d+\.?\d*)\s*kg.*計(\d+\.?\d*)\s*kg', product_name, re.IGNORECASE)
                    
                    if set_match:
                        amount_per_variety = float(set_match.group(1))
                        found_varieties = [v for v in varieties if v in product_name]
                        for variety in found_varieties:
                            results_list.append({
                                '品種': variety,
                                '分量_kg': amount_per_variety * row['数量']
                            })
                    else:
                        match = re.search(r'(\d+\.?\d*)\s*(kg|g)', product_name, re.IGNORECASE)
                        if match:
                            amount = float(match.group(1))
                            unit = match.group(2).lower()
                            if unit == 'g':
                                amount /= 1000
                            for variety in varieties:
                                if variety in product_name:
                                    results_list.append({
                                        '品種': variety,
                                        '分量_kg': amount * row['数量']
                                    })
                                    break
                
                if results_list:
                    results_df = pd.DataFrame(results_list)
                    file_agg = results_df.groupby('品種')['分量_kg'].sum().reset_index()
                    current_file_results = file_agg

            if not current_file_results.empty:
                combined_results_df = pd.concat([combined_results_df, current_file_results], ignore_index=True)

        except Exception as e:
            print(f"ファイルの処理中にエラーが発生しました: {e}")
            continue

    if combined_results_df.empty:
        return pd.DataFrame(columns=['品種', '合計分量_kg'])

    # 全ファイルの結果を統合して最終集計
    final_agg = combined_results_df.groupby('品種')['分量_kg'].sum().reset_index()
    final_agg.rename(columns={'分量_kg': '合計分量_kg'}, inplace=True)

    result = final_agg.to_dict('records')
    
    return jsonify({'result': result})

@app.route('/api/unique', methods=['POST'])
def unique():
    """
    アップロードされた複数のCSVファイルから、各ファイルに含まれる
    ユニークな商品名とそれぞれのカウント数を返します。
    """
    uploaded_files = request.files.getlist('csv_files')
    results = {}

    for file in uploaded_files:
        file_name = file.filename
        
        try:
            # エンコーディングを自動判別
            try:
                file_content = file.stream.read().decode('utf-8')
            except UnicodeDecodeError:
                file.stream.seek(0) # ストリームの位置をリセット
                file_content = file.stream.read().decode('cp932')
            
            df = pd.read_csv(io.StringIO(file_content))
            
            if '商品名' in df.columns:
                # 商品名ごとのカウント数を取得
                product_counts = df['商品名'].value_counts().to_dict()
                results[file_name] = product_counts
            else:
                results[file_name] = "商品名列が見つかりません"
        
        except Exception as e:
            results[file_name] = f"読み込みエラー: {e}"
            
    return jsonify({'result': results})