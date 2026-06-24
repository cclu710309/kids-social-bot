ㄋerspective}
                    - 語氣：{', '.join(tone)} | 教育價值：{', '.join(edu)} | 互動目標：{', '.join(cta)}

                    【📝 文案長度與風格嚴格限制】: 「{text_length}」
                    - 一句話入魂：總字數不超過 50 字。
                    - 微故事：字數嚴格控制在 100~150 字以內。
                    - 情境對話：重現現場對話，字數同樣控制在 150 字以內。

                    【任務要求】
                    1. 幫影片想 3 個吸睛的「短影音大標題」。
                    2. 撰寫【IG 貼文文案】（含豐富表情符號，並加上 #小鳥幼兒園）。
                    3. 撰寫【FB 貼文文案】（結尾帶入互動目標，並同步加上 #小鳥幼兒園 標籤）。
                    4. 附帶一個【AI 小編建議】，簡述這個影片最亮眼、最能打動家長的是哪一個畫面或瞬間。
                    """
                    
                    # 🌟 採用最新一代完全不經由代理、直接與後台直連的生成指令
                    model = genai.GenerativeModel(model_name=target_model)
                    response = model.generate_content([prompt_text, video_file_ai])
                    response_text = response.text

                    try: os.remove(temp_video_path)
                    except: pass

                # --- 🎨 畫面渲染產出結果 ---
                st.success(f"🎉 文案與分析皆已順利產出！")
                
                if "多張活動照片" in upload_mode:
                    match = re.search(r'\[SELECTED_IMAGES\](.*?)\[/SELECTED_IMAGES\]', response_text, re.DOTALL)
                    if match:
                        st.markdown("### 🏆 AI 嚴選最佳照片")
                        st.info("💡 **手機存圖秘訣**：請直接「長按」下方您喜歡的照片，選擇 **「儲存影像」** 即可！")
                        
                        raw_indices = match.group(1).split(',')
                        selected_files = []
                        for idx_str in raw_indices:
                            idx_str = idx_str.strip()
                            if idx_str.isdigit():
                                idx = int(idx_str) - 1
                                if 0 <= idx < len(uploaded_files):
                                    selected_files.append(uploaded_files[idx])
                        
                        if selected_files:
                            img_cols = st.columns(2)
                            for idx, s_file in enumerate(selected_files):
                                original_img = Image.open(s_file)
                                if enable_blur:
                                    final_img = add_blur_padding(original_img)
                                    caption_text = f"精選第 {idx+1} 張 (已防裁切處理)"
                                else:
                                    final_img = original_img
                                    caption_text = f"精選第 {idx+1} 張 (原圖尺寸)"
                                img_cols[idx % 2].image(final_img, use_container_width=True, caption=caption_text)
                    
                    clean_response = re.sub(r'\[SELECTED_IMAGES\].*?\[/SELECTED_IMAGES\]', '', response_text, flags=re.DOTALL).strip()
                    st.markdown("### 📊 文案與詳細建議")
                    st.text_area("您可以直接複製以下全部內容", value=clean_response, height=400)
                else:
                    st.markdown("### 📊 影片文案與標題建議")
                    st.text_area("您可以直接複製以下全部內容", value=response_text, height=400)

            except Exception as e:
                st.error(f"系統偵測到錯誤：{e}")
