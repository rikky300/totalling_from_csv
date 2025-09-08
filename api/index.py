from flask import Flask, request, jsonify, send_from_directory
import pandas as pd
import io

app = Flask(__name__)

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/api/aggregate', methods=['POST'])
def aggregate_csv():
    uploaded_files = request.files.getlist('csv_files')
    
    if not uploaded_files:
        return jsonify({'error': 'ファイルがアップロードされていません。'}), 400

    combined_df_list = []

    for file in uploaded_files:
        try:
            # Shift-JIS (cp932) エンコーディングでファイルを読み込みます
            df = pd.read_csv(io.StringIO(file.stream.read().decode('cp932')))

            df_clean = pd.DataFrame()

            # 商品名列が存在するかをチェック
            if '商品名' not in df.columns:
                print("商品名列が見つかりません。このファイルをスキップします。")
                continue

            df_clean['商品名'] = df['商品名']

            # 数量列を処理
            if '数量' in df.columns:
                df_clean['数量'] = pd.to_numeric(df['数量'], errors='coerce').fillna(1)
            else:
                df_clean['数量'] = 1

            combined_df_list.append(df_clean)

        except Exception as e:
            print(f"ファイルの処理中にエラーが発生しました: {e}")
            return jsonify({'error': 'ファイルの読み込みに失敗しました。'}), 500

    if not combined_df_list:
        return jsonify({'error': '処理できるデータがありませんでした。'}), 400

    combined_df = pd.concat(combined_df_list, ignore_index=True)

    # 商品名でグループ化し、数量の合計を集計します
    aggregated_sales = combined_df.groupby('商品名').agg(
        合計数量=('数量', 'sum')
    ).reset_index()

    # 最終的な結果に含める列を選択
    final_result = aggregated_sales[['商品名', '合計数量']]
    result = final_result.to_dict('records')

    return jsonify({'result': result})

@app.route('/api/totalling', methods=['POST'])
def parse_amount(amount_str):
    """
    文字列から分量（kg）を抽出し、数値に変換する関数。
    例: '500g' -> 0.5, '1.5kg' -> 1.5
    """
    match = re.search(r'(\d+\.?\d*)\s*(kg|g)', str(amount_str), re.IGNORECASE)
    if match:
        amount = float(match.group(1))
        unit = match.group(2).lower()
        if unit == 'g':
            return amount / 1000
        return amount
    return 0.0

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
            df = pd.read_csv(io.StringIO(file.stream.read().decode('cp932')))

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
                df['分量_kg'] = df['分量'].apply(parse_amount)
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