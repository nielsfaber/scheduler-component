cd /config
git clone https://github.com/nielsfaber/scheduler-component.git
mkdir -p custom_components
cp -r scheduler-component/custom_components/scheduler/ custom_components
echo Done setting up
echo Please add the scheduler to your configuration
echo And restart Home Assistant
