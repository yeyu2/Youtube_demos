import openai

response = openai.chat.completions.create(
    model="gpt-4-1106-preview",
    messages=[
        {"role": "system", "content": "Generate response in JSON format"},
        {"role": "user", "content": """List a 3-day travel itinerary to Cebu, 
          including day, meal, hotel, transportaion and sightseeing"""
        }
    ],
    response_format={"type": "json_object"}
)
response_message = response.choices[0].message.content

print(response_message)