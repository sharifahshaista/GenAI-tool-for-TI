import pandas as pd

def clean_tags_and_content(input_csv, output_csv):
    """
    Clean the 'tags' column by removing known promotional text.
    Clean the 'content' column by removing everything up to and including 'Image Credits'.
    If no valid tags remain, leave the field empty.
    If 'Image Credits' not found, leave content unchanged.
    """

    # Load CSV
    try:
        df = pd.read_csv(input_csv)
    except FileNotFoundError:
        print(f"Error: File '{input_csv}' not found")
        return None
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return None

    # --- Clean Tags ---
    if "tags" in df.columns:
        promo_text = (
            "Neon, the No. 2 social app on the Apple App Store, pays users to record their phone calls "
            "and sells data to AI firms, Trump hits H-1B visas with $100,000 fee, targeting the program "
            "that launched Elon Musk and Instagram, Updates to Studio, YouTube Live, new GenAI tools, "
            "and everything else announced at Made on YouTube, Google isn’t kidding around about cost "
            "cutting, even slashing its FT subscription, Meta CTO explains why the smart glasses demos "
            "failed at Meta Connect — and it wasn’t the Wi-Fi, OpenAI’s research on AI models deliberately "
            "lying is wild , How AI startups are fueling Google’s booming cloud business"
        )

        def strip_promo(text):
            if pd.isna(text):
                return ""
            cleaned = text.replace(promo_text, "").strip()
            return cleaned if cleaned else ""

        df["tags"] = df["tags"].apply(strip_promo)
    else:
        print("Warning: 'tags' column not found in CSV")

    # --- Clean Content ---
    if "content" in df.columns:
        def strip_intro(text):
            if pd.isna(text):
                return ""
            marker = "Image Credits"
            if marker in text:
                return text.split(marker, 1)[1].strip()
            return text.strip()

        df["content"] = df["content"].apply(strip_intro)
    else:
        print("Warning: 'content' column not found in CSV")

    # Save cleaned version
    try:
        df.to_csv(output_csv, index=False)
        print(f"Cleaned CSV saved to: {output_csv}")
    except Exception as e:
        print(f"Error saving cleaned CSV: {e}")

    return df


def main():
    INPUT_CSV = "techcrunch_raw.csv"   # change to your actual file
    OUTPUT_CSV = "techcrunch_climate.csv"

    print("Cleaning tags and content columns...")
    clean_df = clean_tags_and_content(INPUT_CSV, OUTPUT_CSV)

    if clean_df is not None:
        print("Cleaning complete! Sample:")
        print(clean_df[["tags", "content"]].head())


if __name__ == "__main__":
    main()

