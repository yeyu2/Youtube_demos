"""
TalentGraph - HR Knowledge Graph Setup Script
Creates a realistic organizational structure for TechNova company
with employees, skills, projects, and reporting relationships.
"""

import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.llm_client.gemini_client import GeminiClient, LLMConfig
from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient
from graphiti_core.nodes import EpisodeType

load_dotenv()

# Configuration
google_api_key = os.environ.get('GOOGLE_API_KEY')
if not google_api_key:
    raise ValueError("GOOGLE_API_KEY environment variable is required")

falkor_host = os.environ.get('FALKORDB_HOST', 'localhost')
falkor_port = os.environ.get('FALKORDB_PORT', '6379')


async def setup_hr_knowledge_graph():
    """
    Set up the TalentGraph HR knowledge base with organizational data.
    """
    
    # Initialize Graphiti
    falkor_driver = FalkorDriver(
        host=falkor_host, 
        port=falkor_port,
        database="talentgraph"
    )
    
    llm_client = GeminiClient(
        config=LLMConfig(
            api_key=google_api_key,
            model="gemini-2.0-flash",
            small_model="gemini-2.0-flash"
        )
    )
    
    embedder = GeminiEmbedder(
        config=GeminiEmbedderConfig(
            api_key=google_api_key,
            embedding_model="gemini-embedding-001"
        )
    )
    
    cross_encoder = GeminiRerankerClient(
        config=LLMConfig(
            api_key=google_api_key,
            model="gemini-2.0-flash"
        )
    )
    
    graphiti = Graphiti(
        graph_driver=falkor_driver,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=cross_encoder
    )
    
    print("=" * 80)
    print("TalentGraph - HR Knowledge Base Setup")
    print("Company: TechNova")
    print("=" * 80)
    
    try:
        # Define organizational episodes
        episodes = [
            # Episode 1: Company and Executive Leadership
            {
                'content': """
                TechNova is a technology company with 50 employees. Sarah Chen is the CTO. 
                Michael Rodriguez is the VP of Engineering, reporting to Sarah Chen.
                Lisa Wang is the VP of Product, also reporting to Sarah Chen.
                """,
                'type': EpisodeType.text,
                'description': 'Company overview and executive structure',
                'timestamp': datetime.now(timezone.utc) - timedelta(days=365)
            },
            
            # Episode 2: Platform Team
            {
                'content': """
                Bob Thompson is the Platform Team Manager, reporting to Michael Rodriguez.
                The Platform Team handles infrastructure and DevOps.
                
                Platform Team members:
                Alice Johnson is a Senior Backend Engineer reporting to Bob Thompson. 
                Alice has skills in Python, Kubernetes, and Docker.
                
                David Kim is a Staff Infrastructure Engineer reporting to Bob Thompson.
                David has expertise in Kubernetes, Terraform, and AWS. He has Level 3 security clearance.
                
                Emily Chen is a DevOps Engineer reporting to Bob Thompson.
                Emily specializes in CI/CD, Jenkins, and monitoring systems.
                """,
                'type': EpisodeType.text,
                'description': 'Platform Team structure',
                'timestamp': datetime.now(timezone.utc) - timedelta(days=200)
            },
            
            # Episode 3: Backend Team
            {
                'content': """
                James Wilson is the Backend Team Manager, reporting to Michael Rodriguez.
                The Backend Team builds APIs and microservices.
                
                Backend Team members:
                Tom Anderson is a Senior Backend Engineer reporting to James Wilson.
                Tom has expertise in Java, Spring Boot, and PostgreSQL.
                
                Rachel Green is a Backend Engineer reporting to James Wilson.
                Rachel specializes in Python, Django, and Redis. She has Level 2 security clearance.
                
                Chris Lee is a Backend Engineer reporting to James Wilson.
                Chris has skills in Node.js, MongoDB, and GraphQL.
                """,
                'type': EpisodeType.text,
                'description': 'Backend Team structure',
                'timestamp': datetime.now(timezone.utc) - timedelta(days=180)
            },
            
            # Episode 4: Frontend Team
            {
                'content': """
                Sophie Martinez is the Frontend Team Manager, reporting to Michael Rodriguez.
                The Frontend Team builds user interfaces and client applications.
                
                Frontend Team members:
                Alex Chen is a Senior Frontend Engineer reporting to Sophie Martinez.
                Alex has expertise in React, TypeScript, and Next.js.
                
                Maria Garcia is a Frontend Engineer reporting to Sophie Martinez.
                Maria specializes in Vue.js, CSS, and responsive design.
                """,
                'type': EpisodeType.text,
                'description': 'Frontend Team structure',
                'timestamp': datetime.now(timezone.utc) - timedelta(days=160)
            },
            
            # Episode 5: Product Team
            {
                'content': """
                Under Lisa Wang (VP of Product), there are two Product Managers:
                
                Kevin Brown is a Senior Product Manager reporting to Lisa Wang.
                Kevin focuses on enterprise features and B2B products.
                
                Nina Patel is a Product Manager reporting to Lisa Wang.
                Nina focuses on AI/ML product features and user analytics.
                """,
                'type': EpisodeType.text,
                'description': 'Product Team structure',
                'timestamp': datetime.now(timezone.utc) - timedelta(days=140)
            },
            
            # Episode 6: Project Assignments
            {
                'content': """
                Project X is a confidential payment system project with high security requirements.
                Team: Alice Johnson (technical lead), Tom Anderson (backend), Emily Chen (DevOps).
                All Project X members have Level 3 security clearance.
                
                The AI Strategy Project focuses on machine learning capabilities.
                Started in February 2024.
                Team: Rachel Green (backend lead), Nina Patel (product), Alex Chen (frontend).
                
                Cloud Migration Project is modernizing infrastructure to AWS.
                Team: David Kim (lead), Chris Lee (backend support).
                """,
                'type': EpisodeType.text,
                'description': 'Project assignments',
                'timestamp': datetime.now(timezone.utc) - timedelta(days=100)
            },
            
            # Episode 7: Skills and Certifications
            {
                'content': """
                Kubernetes experts: Alice Johnson, David Kim, Emily Chen.
                AWS certified: David Kim, Tom Anderson.
                Python specialists: Alice Johnson, Rachel Green.
                React experts: Alex Chen, Maria Garcia.
                
                Tom Anderson has Level 3 security clearance for financial systems.
                Emily Chen has Level 3 clearance and SOC 2 audit certification.
                """,
                'type': EpisodeType.text,
                'description': 'Skills and certifications',
                'timestamp': datetime.now(timezone.utc) - timedelta(days=60)
            },
            
            # Episode 8: Compliance and Audit Status
            {
                'content': """
                Bob Thompson's Platform Team is under SOC 2 compliance audit starting October 2024.
                During the audit, Platform Team members cannot be assigned to new financial projects.
                
                Segregation of Duties (SoD) rules:
                - Employees on financial projects (Project X) cannot work on AI projects.
                - Backend Team members on AI Strategy cannot join Project X.
                
                Security clearance levels:
                Level 3 (financial): Alice Johnson, David Kim, Tom Anderson, Emily Chen.
                Level 2 (sensitive): Rachel Green, Kevin Brown.
                Level 1 (standard): All other employees.
                """,
                'type': EpisodeType.text,
                'description': 'Compliance and security',
                'timestamp': datetime.now(timezone.utc) - timedelta(days=30)
            },
        ]
        
        # Add episodes to the graph with delays to respect rate limits
        print("\n📊 Adding organizational data to knowledge graph...\n")
        
        for i, episode in enumerate(episodes):
            print(f"[{i+1}/{len(episodes)}] Processing: {episode['description']}")
            
            await graphiti.add_episode(
                name=f"TechNova_Org_Episode_{i+1}",
                episode_body=episode['content'],
                source=episode['type'],
                source_description=episode['description'],
                reference_time=episode['timestamp'],
            )
            
            print(f"✅ Added: {episode['description']}")
            
            # Wait between episodes to respect rate limits
            if i < len(episodes) - 1:
                wait_time = 25  # Consistent wait time
                print(f"⏳ Waiting {wait_time} seconds before next episode...\n")
                await asyncio.sleep(wait_time)
        
        print("\n" + "=" * 80)
        print("✅ TalentGraph Setup Complete!")
        print("=" * 80)
        print("\nKnowledge Graph Summary:")
        print("- 15 employees across 4 teams (Platform, Backend, Frontend, Product)")
        print("- 3 active projects (Project X, AI Strategy, Cloud Migration)")
        print("- Reporting structure: CTO → 2 VPs → 5 Managers → 10 Engineers")
        print("- Key skills: Kubernetes, Python, React, Java, AWS, Docker")
        print("- Compliance: SOC 2 audit, SoD rules, 3-level security clearances")
        print("\nThe graph is now ready for HR queries!")
        print("=" * 80)
        
    finally:
        await graphiti.close()
        print("\n🔌 Connection closed")


if __name__ == '__main__':
    asyncio.run(setup_hr_knowledge_graph())
