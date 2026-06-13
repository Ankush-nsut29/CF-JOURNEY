import requests
import json

url = 'https://leetcode.com/graphql'
headers = {'Content-Type': 'application/json'}

query_recent = '''
query recentAcSubmissions($username: String!) {
  recentAcSubmissionList(username: $username, limit: 200) {
    title
    titleSlug
    timestamp
  }
}
'''
res = requests.post(url, json={'query': query_recent, 'variables': {'username': 'isaidduh'}})
data = res.json()
ac_list = data['data']['recentAcSubmissionList']
print('Recent AC limit 200 length:', len(ac_list))

# To get details for a specific problem:
query_question = '''
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    difficulty
    topicTags {
      name
    }
  }
}
'''
res = requests.post(url, json={'query': query_question, 'variables': {'titleSlug': 'two-sum'}})
print('Question Data:', res.text)

# Also test userProfileCalendar
query_cal = '''
query userProfileCalendar($username: String!, $year: Int) {
  matchedUser(username: $username) {
    userCalendar(year: $year) {
      submissionCalendar
    }
  }
}
'''
res = requests.post(url, json={'query': query_cal, 'variables': {'username': 'isaidduh'}})
print('Calendar length:', len(res.text))

