import os
import sys
from pathlib import Path
from git import Repo
import requests
from dotenv import load_dotenv

load_dotenv()

class GitAutomation:
    def __init__(self, git_dir):
        self.token = os.getenv("GITHUB_TOKEN")
        if not self.token:
            print("Error: GITHUB_TOKEN environment variable not set")
            sys.exit(1)
  
        git_ssh_identity_file = os.path.join(os.getcwd(),'id_rsa')
        self.git_ssh_cmd = 'ssh -i %s' % git_ssh_identity_file

        self.main_git_dir = Path(git_dir) / "main_git_dir"
        self.github_api_url = "https://api.github.com"
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def check_fork_exists(self, owner, repo_name):
        response = requests.get(f"{self.github_api_url}/repos/{owner}/{repo_name}", headers=self.headers)
        
        if response.status_code == 200:
            return True
        print("Failed to check forks:", response.json())
        return False

    def fork_repo(self, repo_url):
        """Fork the repository."""
        owner = repo_url.split("/")[-2]
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        response = requests.post(f"{self.github_api_url}/repos/{owner}/{repo_name}/forks", headers=self.headers)
        if response.status_code == 202:
            return True
        print("Failed to fork repository:", response.json())
        return False

    def checkout_new_branch(self, branch_name):
        """Check out a new branch."""
        try:
            repo = Repo(self.main_git_dir)
            repo.git.checkout("-b", branch_name)
            return True
        except Exception as e:
            print(f"Error checking out new branch: {e}")
            return False

    def commit_and_push(self, file_path=None, message="Update changes"):
        """Commit and push changes."""
        try:
            repo = Repo(self.main_git_dir)
            with repo.git.custom_environment(GIT_SSH_COMMAND=self.git_ssh_cmd):
                if file_path:
                    if os.path.exists(os.path.join(self.main_git_dir, file_path)):
                        repo.git.add(file_path)
                    else:
                        print(f"Error: {file_path} does not exist.")
                        return False
                else:
                    repo.git.add(all=True)
                repo.git.commit(m=message)
                origin = repo.remotes.origin
                repo.git.push('--set-upstream', origin, repo.active_branch.name)
                return True
        except Exception as e:
            print(f"Error committing and pushing changes: {e}")
            return False

    def create_pr(self, original_owner, current_owner, repo_name, base_branch="main", head_branch="main", title="Sync changes"):
        """Create a pull request to the original repository."""
        payload = {
            "title": title,
            "head": f"{current_owner}:{head_branch}",
            "base": base_branch
        }
        response = requests.post(f"{self.github_api_url}/repos/{original_owner}/{repo_name}/pulls", headers=self.headers, json=payload)
        if response.status_code == 201:
            return True
        print("Failed to create pull request:", response.json())
        return False

    def sync_fork(self, repo_url, fork_url):
        """Sync fork with the main branch."""
        try:
            # Clone or open the fork repository
            if not os.path.exists(self.main_git_dir):
                Repo.clone_from(fork_url, self.main_git_dir)
            fork_repo = Repo(self.main_git_dir)
            origin = fork_repo.remotes.origin
            
            # Add the original repository as upstream
            if 'upstream' not in [remote.name for remote in fork_repo.remotes]:
                fork_repo.create_remote('upstream', repo_url)
            upstream = fork_repo.remotes.upstream
            
            # Fetch the latest changes
            upstream.fetch()
            
            # Checkout and merge the upstream main branch into the fork's main branch
            fork_repo.git.checkout("main")
            fork_repo.git.merge("upstream/main")
            
            # Push changes to the fork's remote repository
            origin.push()
            # Remove origin
            # fork_repo.delete_remote("upstream")
            return True
        except Exception as e:
            print(f"Error syncing fork: {e}")
            return False

    def clone_repo(self, repo_url):
        """Clone the forked repository."""
        try:
            Repo.clone_from(repo_url, self.main_git_dir)
            return True
        except Exception as e:
            print(f"Error cloning fork: {e}")
            return False
    