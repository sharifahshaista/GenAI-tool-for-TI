# Using LM Studio with First-pass Summarization

This guide explains how to use local models from LM Studio instead of Azure OpenAI for summarization.

---

## 🎯 Overview

You can now choose between:
- **Azure OpenAI** - Cloud-based models (GPT-4, GPT-4o, etc.)
- **LM Studio (Local)** - Run models locally on your machine

---

## 📥 Setup LM Studio

### 1. Install LM Studio
- Download from: https://lmstudio.ai/
- Install and launch the application

### 2. Download a Model
In LM Studio:
1. Go to the "Discover" tab
2. Search for recommended models:
   - **Llama 3.1 8B** (good balance of speed/quality)
   - **Llama 3.2 3B** (faster, lower quality)
   - **Mistral 7B** (good for technical content)
   - **Qwen 2.5 7B** (excellent for summarization)
3. Click "Download" on your chosen model

### 3. Load the Model
1. Go to the "Local Server" tab
2. Select your downloaded model from the dropdown
3. Click "Start Server"
4. Server will start at `http://127.0.0.1:1234`

**Note:** If you access this URL in your browser, you'll see an error like:
```
{"error":"Unexpected endpoint or method. (GET /v1)"}
```
This is **normal and expected** ✅ - it means the server is running correctly!

---

## 🚀 Using in the App

### 1. Select LM Studio Provider

In the First-pass Summarization page:

1. Under "🤖 Model Selection"
2. Select **"LM Studio (Local)"** from the Provider dropdown
3. Verify the URL is `http://127.0.0.1:1234/v1`
4. You should see: "💡 Make sure LM Studio is running and a model is loaded"

### 2. Upload and Process CSV

Follow the normal CSV upload process:
1. Upload your CSV file with a 'content' column
2. Click "Start Summarization"
3. The app will use your local LM Studio model instead of Azure OpenAI

---

## ⚙️ Configuration Options

### Default URL
```
http://127.0.0.1:1234/v1
```

### Custom Port
If LM Studio is running on a different port:
1. Change the port in LM Studio settings
2. Update the URL in the app accordingly (e.g., `http://127.0.0.1:5000/v1`)

### Model Selection
- LM Studio uses whatever model is currently loaded
- To change models: Stop the server → Select different model → Restart server

---

## 🔍 Troubleshooting

### Browser Shows: "Unexpected endpoint or method"
**This is NORMAL!** ✅
- When you access `http://127.0.0.1:1234/v1` in your browser, you see an error
- This is expected - browsers use GET requests, the API expects POST
- **Your app will work fine** - it uses the correct endpoints internally

**To verify it's actually working, run this test:**
```bash
curl -X POST http://127.0.0.1:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "local-model", "messages": [{"role": "user", "content": "Hello"}]}'
```

If you get a JSON response with "choices", it's working! ✅

### Error: "Connection refused"
**Cause:** LM Studio server is not running
**Solution:** 
1. Open LM Studio
2. Go to "Local Server" tab
3. Ensure a model is selected
4. Click "Start Server"

### Error: "Model not found"
**Cause:** No model is loaded in LM Studio
**Solution:**
1. Download a model from the "Discover" tab
2. Go to "Local Server" tab
3. Select the model from dropdown
4. Click "Start Server"

### Slow Processing
**Cause:** Model is too large for your hardware
**Solution:**
- Use a smaller model (3B parameters instead of 8B+)
- Close other applications
- Check LM Studio's performance settings

### Poor Quality Summaries
**Cause:** Model may not be suitable for technical content
**Solution:**
- Try a different model (Qwen 2.5 or Mistral work well)
- Adjust temperature in LM Studio settings (try 0.3-0.7)

---

## 📊 Model Recommendations

### For Speed (Fast processing, acceptable quality)
- **Llama 3.2 3B** - Small, fast
- **Phi-3 Mini** - Efficient, good for short content

### For Quality (Best summaries, slower)
- **Llama 3.1 8B** - Balanced performance
- **Qwen 2.5 7B** - Excellent for summarization
- **Mistral 7B v0.3** - Good for technical content

### For Very Long Content
- **Llama 3.1 8B** - 128K context window
- **Qwen 2.5 7B** - 32K context window

---

## 💡 Performance Tips

### 1. GPU Acceleration
- LM Studio automatically uses GPU if available
- NVIDIA GPUs work best (CUDA support)
- Apple Silicon Macs use Metal acceleration

### 2. Batch Size
- LM Studio handles this automatically
- Larger models may process slower but produce better results

### 3. Context Length
- Longer content = slower processing
- Consider truncating very long articles if speed is critical

### 4. Temperature Settings
In LM Studio server settings:
- **Low (0.1-0.3)**: More factual, deterministic summaries
- **Medium (0.5-0.7)**: Balanced creativity and accuracy
- **High (0.8-1.0)**: More creative, less predictable

---

## 🔐 Privacy & Security

### Advantages of Local Models
✅ **Complete Privacy**: Data never leaves your machine
✅ **No API Costs**: Unlimited usage, no per-token charges
✅ **Offline Capability**: Works without internet
✅ **Full Control**: Choose any model, adjust all settings

### Trade-offs
⚠️ **Speed**: Local models may be slower than cloud APIs
⚠️ **Quality**: Smaller local models may not match GPT-4 quality
⚠️ **Hardware**: Requires decent CPU/GPU and RAM

---

## 🆚 Comparison: Azure OpenAI vs LM Studio

| Feature | Azure OpenAI | LM Studio |
|---------|--------------|-----------|
| **Cost** | Pay per token | Free (after model download) |
| **Privacy** | Data sent to cloud | Fully local |
| **Speed** | Fast (cloud) | Depends on hardware |
| **Quality** | Excellent (GPT-4) | Good (depends on model) |
| **Setup** | API key needed | Software install + model download |
| **Internet** | Required | Not required |
| **Context Limit** | Up to 128K tokens | Depends on model (8K-128K) |

---

## 📝 Example Workflow

### Using LM Studio for a CSV with 100 rows:

1. **Preparation**
   - Start LM Studio
   - Load Llama 3.1 8B model
   - Start local server

2. **In the App**
   - Select "LM Studio (Local)" provider
   - Verify URL: `http://127.0.0.1:1234/v1`
   - Upload your CSV file
   - Click "Start Summarization"

3. **Processing**
   - Each row is sent to your local model
   - Summaries generated locally (no cloud API calls)
   - Progress tracked with time estimates

4. **Results**
   - Same output format as Azure OpenAI
   - Summaries and classifications saved to CSV
   - Available in Database view

---

## 🔧 Advanced Configuration

### Custom System Prompts
The tech-intelligence prompt is built into the code. To customize:
1. Edit `agents/summarise_csv.py`
2. Modify `TECH_INTEL_PROMPT` variable
3. Restart the Streamlit app

### Multiple LM Studio Instances
You can run multiple LM Studio instances on different ports:
```
Instance 1: http://127.0.0.1:1234/v1
Instance 2: http://127.0.0.1:5678/v1
```
Update the URL in the app to switch between them.

---

## 📚 Recommended Reading

- [LM Studio Documentation](https://lmstudio.ai/docs)
- [Hugging Face Model Hub](https://huggingface.co/models) - Browse available models
- [Ollama](https://ollama.ai/) - Alternative to LM Studio (also compatible)

---

## ❓ FAQ

**Q: Can I use both Azure and LM Studio in the same session?**
A: Yes! Switch providers before each summarization task.

**Q: Which is better for my use case?**
A: 
- **Azure OpenAI**: Best quality, fastest cloud processing, costs money
- **LM Studio**: Free, private, good quality, requires local hardware

**Q: Can I use other OpenAI-compatible services?**
A: Yes! Update the base URL to point to services like:
- **Ollama**: `http://localhost:11434/v1`
- **LocalAI**: Custom port
- **Text Generation WebUI**: Custom port

**Q: How much RAM do I need?**
A: 
- 3B models: 4-8 GB RAM
- 7B models: 8-16 GB RAM
- 8B models: 16-32 GB RAM

**Q: Is LM Studio free?**
A: Yes, LM Studio is free for personal and commercial use.

---

## 🎉 Summary

You now have **flexible model selection** in your First-pass Summarization feature:

✅ Use **Azure OpenAI** for maximum quality and speed (paid)
✅ Use **LM Studio** for privacy, cost savings, and offline capability (free)
✅ Switch between providers anytime
✅ Same output format regardless of provider

Choose the option that best fits your needs! 🚀

